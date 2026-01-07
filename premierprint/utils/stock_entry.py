"""Stock Entry utilities and hooks for Premier Print.

This module provides:
1. Query functions for Sales Order Item dropdown
2. BOM material explosion logic
3. on_submit hook for inter-company transfer automation with SMART WAREHOUSE LOGIC

SMART WAREHOUSE LOGIC:
- Source Company: Detected from doc.company (standard field)
- Target Company: Detected from t_warehouse.company (automatic)
- No need for custom_from_sub_company or custom_to_sub_company fields
"""

import logging
from typing import Dict, List, Optional

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, nowdate

logger = logging.getLogger(__name__)


@frappe.whitelist()
def get_sales_order_items_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict) -> List[tuple]:
    """Custom query for Sales Order Item dropdown.

    Returns item_name instead of item_code for better UX.
    Filters by sales_order if provided.

    Args:
        doctype: Target doctype (Sales Order Item)
        txt: Search text entered by user
        searchfield: Field being searched (name by default)
        start: Pagination start
        page_len: Page size
        filters: Additional filters (sales_order)

    Returns:
        List of tuples: [(name, item_name, item_code, qty), ...]
    """
    conditions = []
    values = []

    if filters.get("parent"):
        conditions.append("soi.parent = %s")
        values.append(filters["parent"])

    if txt:
        conditions.append("(soi.item_name LIKE %s OR soi.item_code LIKE %s OR soi.name LIKE %s)")
        search_txt = f"%{txt}%"
        values.extend([search_txt, search_txt, search_txt])

    where_clause = " AND " + " AND ".join(conditions) if conditions else ""

    query = f"""
        SELECT
            soi.name,
            soi.item_name,
            soi.item_code,
            soi.qty,
            soi.uom
        FROM
            `tabSales Order Item` soi
        INNER JOIN
            `tabSales Order` so ON soi.parent = so.name
        WHERE
            so.docstatus = 1
            {where_clause}
        ORDER BY
            soi.creation DESC
        LIMIT {start}, {page_len}
    """

    return frappe.db.sql(query, tuple(values))


@frappe.whitelist()
def get_bom_materials(sales_order_item: str) -> List[Dict]:
    """Explode BOM and return raw materials for a Sales Order Item.

    Args:
        sales_order_item: Sales Order Item name (ID)

    Returns:
        List of dict with item details:
        [
            {
                "item_code": str,
                "item_name": str,
                "qty": float,
                "uom": str,
                "stock_uom": str,
                "conversion_factor": float,
                "description": str,
                "has_batch_no": int,
                "has_serial_no": int,
            },
            ...
        ]
    """
    if not sales_order_item:
        frappe.throw(_("Sales Order Item is required"))

    # Get Sales Order Item details
    soi = frappe.db.get_value(
        "Sales Order Item",
        sales_order_item,
        ["item_code", "qty", "bom", "uom", "parent"],
        as_dict=1
    )

    if not soi:
        frappe.throw(_("Sales Order Item {0} not found").format(sales_order_item))

    if not soi.bom:
        frappe.throw(_("No BOM found for Item {0} in Sales Order Item {1}").format(
            soi.item_code, sales_order_item
        ))

    # Get default BOM if not specified
    bom = soi.bom or frappe.db.get_value("Item", soi.item_code, "default_bom")

    if not bom:
        frappe.throw(_("No BOM configured for Item {0}").format(soi.item_code))

    # Explode BOM
    from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict

    bom_items = get_bom_items_as_dict(
        bom=bom,
        company=frappe.db.get_value("Sales Order", soi.parent, "company"),
        qty=soi.qty,
        fetch_exploded=1,  # Get raw materials, not sub-assemblies
        fetch_qty_in_stock_uom=False
    )

    materials = []
    for item_code, item_data in bom_items.items():
        item_details = frappe.db.get_value(
            "Item",
            item_code,
            ["item_name", "stock_uom", "description", "has_batch_no", "has_serial_no"],
            as_dict=1
        )

        materials.append({
            "item_code": item_code,
            "item_name": item_details.item_name,
            "qty": flt(item_data.qty),
            "uom": item_data.stock_uom or item_details.stock_uom,
            "stock_uom": item_details.stock_uom,
            "conversion_factor": item_data.conversion_factor or 1.0,
            "description": item_details.description or "",
            "has_batch_no": item_details.has_batch_no or 0,
            "has_serial_no": item_details.has_serial_no or 0,
            "bom_no": bom,
        })

    return materials


def on_submit_stock_entry(doc: Document, method: str = None) -> None:
    """Hook executed on Stock Entry submit.

    SMART WAREHOUSE LOGIC for "Перемещение" type:
    - Source Company: From doc.company (standard field)
    - Target Company: Detected from t_warehouse.company (automatic detection)
    - If Source Company != Target Company:
      * Creates Sales Invoice (draft) from source to target
      * Creates Purchase Receipt (draft) from target to source
      * Auto-creates Customer/Supplier links if missing
      * update_stock=0 (Stock Entry already handled stock movement)

    Args:
        doc: Stock Entry document
        method: Hook method name (not used)
    """
    # Only process "Перемещение" type
    if doc.stock_entry_type != "Перемещение":
        return

    if not doc.items:
        return

    logger.info("Processing inter-company transfer for Stock Entry: %s", doc.name)

    # Group items by company pair (source_company, target_company)
    # Source company is always doc.company
    # Target company is detected from t_warehouse
    company_transfers = {}

    for item in doc.items:
        if not item.s_warehouse or not item.t_warehouse:
            continue

        # SMART DETECTION: Get companies from warehouses
        source_company = doc.company  # Use standard company field as source
        target_company = frappe.db.get_value("Warehouse", item.t_warehouse, "company")

        if not source_company or not target_company:
            logger.warning(
                "Company not found for item %s (source: %s, target warehouse: %s)",
                item.item_code, source_company, item.t_warehouse
            )
            continue

        # Verify s_warehouse belongs to source company
        s_warehouse_company = frappe.db.get_value("Warehouse", item.s_warehouse, "company")
        if s_warehouse_company != source_company:
            frappe.msgprint(
                _("Warning: Source warehouse {0} belongs to {1}, but document company is {2}").format(
                    item.s_warehouse, s_warehouse_company, source_company
                ),
                indicator="orange"
            )

        # Only create documents for inter-company transfers
        if source_company == target_company:
            logger.info(
                "Skipping internal transfer for item %s (same company: %s)",
                item.item_code, source_company
            )
            continue

        key = (source_company, target_company)
        if key not in company_transfers:
            company_transfers[key] = []

        company_transfers[key].append(item)

    # Create documents for each company pair
    for (source_company, target_company), items in company_transfers.items():
        try:
            _create_inter_company_documents(
                stock_entry=doc,
                source_company=source_company,
                target_company=target_company,
                items=items
            )
        except Exception as e:
            logger.exception(
                "Failed to create inter-company documents for %s -> %s: %s",
                source_company, target_company, str(e)
            )
            frappe.msgprint(
                _("Warning: Could not create inter-company documents for {0} -> {1}: {2}").format(
                    source_company, target_company, str(e)
                ),
                indicator="orange"
            )


def _create_inter_company_documents(
    stock_entry: Document,
    source_company: str,
    target_company: str,
    items: List
) -> None:
    """Create Sales Invoice and Purchase Receipt for inter-company transfer.

    Args:
        stock_entry: Original Stock Entry document
        source_company: Company sending materials (from doc.company)
        target_company: Company receiving materials (from t_warehouse.company)
        items: List of Stock Entry Detail items
    """
    # Ensure Customer/Supplier relationships exist
    customer = _ensure_customer_link(source_company, target_company)
    supplier = _ensure_supplier_link(source_company, target_company)

    # Create Sales Invoice (from source to target)
    sales_invoice = _create_sales_invoice(
        stock_entry=stock_entry,
        company=source_company,
        customer=customer,
        items=items
    )

    # Create Purchase Receipt (from target receiving from source)
    purchase_receipt = _create_purchase_receipt(
        stock_entry=stock_entry,
        company=target_company,
        supplier=supplier,
        items=items
    )

    frappe.msgprint(
        _("Created inter-company documents:<br>Sales Invoice: {0}<br>Purchase Receipt: {1}").format(
            f'<a href="/app/sales-invoice/{sales_invoice.name}">{sales_invoice.name}</a>',
            f'<a href="/app/purchase-receipt/{purchase_receipt.name}">{purchase_receipt.name}</a>'
        ),
        indicator="green",
        alert=True
    )


def _ensure_customer_link(source_company: str, target_company: str) -> str:
    """Ensure target company exists as Customer for source company.

    Args:
        source_company: Selling company
        target_company: Buying company (to be created as Customer)

    Returns:
        Customer name
    """
    # Check if Customer already exists
    customer_name = frappe.db.get_value(
        "Customer",
        {"customer_name": target_company, "represents_company": target_company}
    )

    if customer_name:
        return customer_name

    # Create new Customer
    customer = frappe.new_doc("Customer")
    customer.customer_name = target_company
    customer.customer_type = "Company"
    customer.represents_company = target_company
    customer.customer_group = "Commercial"  # Default group
    customer.territory = "Uzbekistan"  # Default territory
    customer.insert(ignore_permissions=True)

    logger.info("Created Customer: %s for Company: %s", customer.name, target_company)
    return customer.name


def _ensure_supplier_link(source_company: str, target_company: str) -> str:
    """Ensure source company exists as Supplier for target company.

    Args:
        source_company: Selling company (to be created as Supplier)
        target_company: Buying company

    Returns:
        Supplier name
    """
    # Check if Supplier already exists
    supplier_name = frappe.db.get_value(
        "Supplier",
        {"supplier_name": source_company, "represents_company": source_company}
    )

    if supplier_name:
        return supplier_name

    # Create new Supplier
    supplier = frappe.new_doc("Supplier")
    supplier.supplier_name = source_company
    supplier.supplier_type = "Company"
    supplier.represents_company = source_company
    supplier.supplier_group = "Services"  # Default group
    supplier.country = "Uzbekistan"
    supplier.insert(ignore_permissions=True)

    logger.info("Created Supplier: %s for Company: %s", supplier.name, source_company)
    return supplier.name


def _create_sales_invoice(
    stock_entry: Document,
    company: str,
    customer: str,
    items: List
) -> Document:
    """Create Sales Invoice (draft) for inter-company transfer.

    Args:
        stock_entry: Source Stock Entry
        company: Selling company
        customer: Buying customer
        items: Items being transferred

    Returns:
        Sales Invoice document (draft)
    """
    si = frappe.new_doc("Sales Invoice")
    si.company = company
    si.customer = customer
    si.posting_date = stock_entry.posting_date or nowdate()
    si.set_posting_time = 1
    si.update_stock = 0  # Stock Entry already updated stock

    # Reference to Stock Entry
    if hasattr(si, 'custom_stock_entry'):
        si.custom_stock_entry = stock_entry.name

    # Add items
    for item in items:
        si.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": flt(item.qty),
            "uom": item.uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": item.conversion_factor or 1.0,
            "rate": flt(item.basic_rate) or flt(item.valuation_rate) or 0,
            "warehouse": item.s_warehouse,  # Selling from source warehouse
        })

    si.flags.ignore_permissions = True
    si.flags.ignore_mandatory = True
    si.insert()

    logger.info("Created Sales Invoice: %s for Stock Entry: %s", si.name, stock_entry.name)
    return si


def _create_purchase_receipt(
    stock_entry: Document,
    company: str,
    supplier: str,
    items: List
) -> Document:
    """Create Purchase Receipt (draft) for inter-company transfer.

    Args:
        stock_entry: Source Stock Entry
        company: Buying company
        supplier: Selling supplier
        items: Items being received

    Returns:
        Purchase Receipt document (draft)
    """
    pr = frappe.new_doc("Purchase Receipt")
    pr.company = company
    pr.supplier = supplier
    pr.posting_date = stock_entry.posting_date or nowdate()
    pr.set_posting_time = 1
    pr.update_stock = 0  # Stock Entry already updated stock

    # Reference to Stock Entry
    if hasattr(pr, 'custom_stock_entry'):
        pr.custom_stock_entry = stock_entry.name

    # Add items
    for item in items:
        pr.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": flt(item.qty),
            "uom": item.uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": item.conversion_factor or 1.0,
            "rate": flt(item.basic_rate) or flt(item.valuation_rate) or 0,
            "warehouse": item.t_warehouse,  # Receiving to target warehouse
        })

    pr.flags.ignore_permissions = True
    pr.flags.ignore_mandatory = True
    pr.insert()

    logger.info("Created Purchase Receipt: %s for Stock Entry: %s", pr.name, stock_entry.name)
    return pr
