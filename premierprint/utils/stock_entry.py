"""Stock Entry utilities and hooks for Premier Print.

This module provides:
1. Query functions for Sales Order Item dropdown
2. BOM material explosion logic
3. on_submit hook for inter-company transfer automation

SMART WAREHOUSE LOGIC:
- Source Company: Detected from s_warehouse.company
- Target Company: Detected from t_warehouse.company
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
def get_sales_order_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict) -> List[tuple]:
    """Custom query for Sales Order dropdown.

    Shows customer_name + title first, then SO name for better UX.

    Returns:
        List of tuples: [(name, customer_name, grand_total, transaction_date), ...]
    """
    search_txt = f"%{txt}%"

    return frappe.db.sql("""
        SELECT
            so.name,
            so.customer_name,
            so.grand_total,
            so.transaction_date
        FROM
            `tabSales Order` so
        WHERE
            so.docstatus = 1
            AND so.status NOT IN ('Closed', 'Cancelled')
            AND (so.name LIKE %(txt)s OR so.customer_name LIKE %(txt)s OR so.title LIKE %(txt)s)
        ORDER BY
            so.transaction_date DESC, so.creation DESC
        LIMIT %(start)s, %(page_len)s
    """, {
        "txt": search_txt,
        "start": int(start),
        "page_len": int(page_len)
    })


@frappe.whitelist()
def get_sales_order_items_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict) -> List[tuple]:
    """Custom query for Sales Order Item dropdown.

    Returns item_name first for better UX.
    Filters by sales_order (parent) if provided.

    Args:
        doctype: Target doctype (Sales Order Item)
        txt: Search text entered by user
        searchfield: Field being searched (name by default)
        start: Pagination start
        page_len: Page size
        filters: Additional filters (sales_order or parent)

    Returns:
        List of tuples: [(name, item_name, item_code, qty, uom), ...]
    """
    # Get sales_order from filters - can be "parent" or "sales_order"
    sales_order = filters.get("parent") or filters.get("sales_order") if filters else None
    search_txt = f"%{txt}%"

    if not sales_order:
        # No Sales Order filter - return empty to force selection
        return []

    return frappe.db.sql("""
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
            AND soi.parent = %(sales_order)s
            AND (soi.item_name LIKE %(txt)s OR soi.item_code LIKE %(txt)s OR soi.name LIKE %(txt)s)
        ORDER BY
            soi.idx ASC
        LIMIT %(start)s, %(page_len)s
    """, {
        "sales_order": sales_order,
        "txt": search_txt,
        "start": int(start),
        "page_len": int(page_len)
    })


@frappe.whitelist()
def get_sales_order_item_query(doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: Dict) -> List[tuple]:
    """Query for Item in Stock Entry items table - filtered by Sales Order.

    Shows item_name prominently in dropdown, filters by Sales Order if provided.
    Returns: [(item_code, item_name, qty, stock_uom), ...]

    Args:
        doctype: Target doctype (Item)
        txt: Search text entered by user
        searchfield: Field being searched
        start: Pagination start
        page_len: Page size
        filters: Additional filters (sales_order)

    Returns:
        List of tuples for awesomplete dropdown
    """
    sales_order = filters.get("sales_order") if filters else None
    search_txt = f"%{txt}%"

    if not sales_order:
        # No Sales Order - return all items with item_name first
        return frappe.db.sql("""
            SELECT 
                item.name as item_code,
                item.item_name,
                item.item_group,
                item.stock_uom
            FROM `tabItem` item
            WHERE item.disabled = 0
                AND (item.name LIKE %(txt)s OR item.item_name LIKE %(txt)s)
            ORDER BY item.item_name
            LIMIT %(start)s, %(page_len)s
        """, {
            "txt": search_txt,
            "start": int(start),
            "page_len": int(page_len)
        })

    # Filter by Sales Order items - show only items from that Sales Order
    return frappe.db.sql("""
        SELECT DISTINCT 
            item.name as item_code,
            item.item_name,
            soi.qty,
            item.stock_uom
        FROM `tabSales Order Item` soi
        INNER JOIN `tabItem` item ON soi.item_code = item.name
        INNER JOIN `tabSales Order` so ON soi.parent = so.name
        WHERE soi.parent = %(sales_order)s
            AND so.docstatus = 1
            AND (item.name LIKE %(txt)s OR item.item_name LIKE %(txt)s)
        ORDER BY item.item_name
        LIMIT %(start)s, %(page_len)s
    """, {
        "sales_order": sales_order,
        "txt": search_txt,
        "start": int(start),
        "page_len": int(page_len)
    })


@frappe.whitelist()
def get_bom_materials(sales_order_item: str = None, sales_order_item_id: str = None) -> List[Dict]:
    """Explode BOM and return raw materials for a Sales Order Item.

    Args:
        sales_order_item: Sales Order Item name (ID) - primary param
        sales_order_item_id: Alias for sales_order_item (for backwards compatibility)

    Returns:
        List of dict with item details
    """
    # Accept either parameter name
    soi_name = sales_order_item or sales_order_item_id
    
    if not soi_name:
        frappe.throw(_("Sales Order Item is required"))

    # Get Sales Order Item details (without bom field - it doesn't exist)
    soi = frappe.db.get_value(
        "Sales Order Item",
        soi_name,
        ["item_code", "qty", "uom", "parent"],
        as_dict=1
    )

    if not soi:
        frappe.throw(_("Sales Order Item {0} not found").format(soi_name))

    # Get default BOM from Item
    bom = frappe.db.get_value("Item", soi.item_code, "default_bom")

    if not bom:
        frappe.throw(_("No BOM configured for Item {0}").format(soi.item_code))

    # Explode BOM
    from erpnext.manufacturing.doctype.bom.bom import get_bom_items_as_dict

    bom_items = get_bom_items_as_dict(
        bom=bom,
        company=frappe.db.get_value("Sales Order", soi.parent, "company"),
        qty=soi.qty,
        fetch_exploded=1,
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


def before_validate_stock_entry(doc: Document, method: str = None) -> None:
    """Hook executed before Stock Entry validation.

    For 'Перемещение' type, monkey-patch validate_warehouse_company
    to skip validation. This is necessary because ERPNext doesn't check flags.

    Args:
        doc: Stock Entry document
        method: Hook method name (not used)
    """
    if doc.stock_entry_type == "Перемещение":
        # Import and patch the validation function
        import erpnext.stock.utils as stock_utils
        
        # Check if already patched
        if not getattr(stock_utils, '_original_validate_warehouse_company', None):
            # Store original function
            stock_utils._original_validate_warehouse_company = stock_utils.validate_warehouse_company
            
            def _patched_validate_warehouse_company(warehouse, company):
                """Patched version that respects ignore flag."""
                if getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
                    return
                return stock_utils._original_validate_warehouse_company(warehouse, company)
            
            # Apply patch
            stock_utils.validate_warehouse_company = _patched_validate_warehouse_company
            logger.info("Applied monkey patch to validate_warehouse_company")
        
        # Set flag to trigger the bypass
        frappe.flags.ignore_validate_warehouse_company = True
        doc.flags.ignore_validate_warehouse_company = True
        
        logger.info(
            "Set ignore_validate_warehouse_company flag for Stock Entry: %s",
            doc.name
        )


def on_submit_stock_entry(doc: Document, method: str = None) -> None:
    """Hook executed on Stock Entry submit.

    For 'Перемещение' type, automatically creates inter-company documents
    when source and target warehouses belong to different companies.

    Creates:
    - Sales Invoice (update_stock=0) in source company
    - Purchase Invoice (update_stock=0) in target company

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

    try:
        auto_create_inter_company_docs(doc)
    except Exception as e:
        logger.exception("Error in inter-company transfer: %s", str(e))
        frappe.msgprint(
            _("Warning: Error creating inter-company documents: {0}").format(str(e)),
            indicator="orange"
        )


def auto_create_inter_company_docs(doc: Document) -> None:
    """Automatically create Sales Invoice and Purchase Invoice for inter-company transfers.

    Algorithm:
    1. Loop through items
    2. Get source_company from s_warehouse.company
    3. Get target_company from t_warehouse.company
    4. If source != target: Create SI (draft) and PI (draft)
    5. Show HTML links to created documents

    IMPORTANT: Stock Entry already updated stock ledger.
    - Sales Invoice: update_stock=0 (accounting only)
    - Purchase Invoice: update_stock=0 (accounting only)
    This prevents double stock counting in target warehouse.

    Args:
        doc: Stock Entry document
    """
    # Group items by company pair
    company_transfers = {}

    for item in doc.items:
        if not item.s_warehouse or not item.t_warehouse:
            continue

        # Get companies from warehouses
        source_company = frappe.db.get_value("Warehouse", item.s_warehouse, "company")
        target_company = frappe.db.get_value("Warehouse", item.t_warehouse, "company")

        if not source_company or not target_company:
            logger.warning(
                "Company not found for item %s (s_warehouse: %s, t_warehouse: %s)",
                item.item_code, item.s_warehouse, item.t_warehouse
            )
            continue

        # Skip internal transfers (same company)
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
    created_docs = []
    
    for (source_company, target_company), items in company_transfers.items():
        try:
            # Ensure Customer/Supplier relationships exist
            customer = _ensure_customer_link(source_company, target_company)
            supplier = _ensure_supplier_link(source_company, target_company)

            # Create Sales Invoice (from source to target)
            sales_invoice = _create_sales_invoice(
                stock_entry=doc,
                company=source_company,
                customer=customer,
                items=items
            )

            # Create Purchase Invoice (target buying from source)
            purchase_invoice = _create_purchase_invoice(
                stock_entry=doc,
                company=target_company,
                supplier=supplier,
                items=items
            )

            created_docs.append({
                "source": source_company,
                "target": target_company,
                "si": sales_invoice.name,
                "pi": purchase_invoice.name
            })

        except Exception as e:
            logger.exception(
                "Failed to create inter-company documents for %s -> %s: %s",
                source_company, target_company, str(e)
            )
            frappe.msgprint(
                _("Warning: Could not create documents for {0} → {1}: {2}").format(
                    source_company, target_company, str(e)
                ),
                indicator="orange"
            )

    # Show success message with HTML links
    if created_docs:
        _show_success_message(created_docs)


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
    customer.customer_group = frappe.db.get_single_value("Selling Settings", "customer_group") or "Commercial"
    customer.territory = frappe.db.get_single_value("Selling Settings", "territory") or "All Territories"
    customer.insert(ignore_permissions=True)

    logger.info("Created Customer: %s for Company: %s", customer.name, target_company)
    frappe.msgprint(_("Auto-created Customer: {0}").format(customer.name), indicator="blue")
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
    supplier.supplier_group = frappe.db.get_single_value("Buying Settings", "supplier_group") or "Services"
    supplier.insert(ignore_permissions=True)

    logger.info("Created Supplier: %s for Company: %s", supplier.name, source_company)
    frappe.msgprint(_("Auto-created Supplier: {0}").format(supplier.name), indicator="blue")
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
            "warehouse": item.s_warehouse,
        })

    si.flags.ignore_permissions = True
    si.flags.ignore_mandatory = True
    si.insert()

    logger.info("Created Sales Invoice: %s for Stock Entry: %s", si.name, stock_entry.name)
    return si


def _create_purchase_invoice(
    stock_entry: Document,
    company: str,
    supplier: str,
    items: List
) -> Document:
    """Create Purchase Invoice (draft) for inter-company transfer.

    Args:
        stock_entry: Source Stock Entry
        company: Buying company
        supplier: Selling supplier
        items: Items being purchased

    Returns:
        Purchase Invoice document (draft)
    """
    pi = frappe.new_doc("Purchase Invoice")
    pi.company = company
    pi.supplier = supplier
    pi.posting_date = stock_entry.posting_date or nowdate()
    pi.set_posting_time = 1
    pi.update_stock = 0  # Stock Entry already updated stock

    # Reference to Stock Entry
    if hasattr(pi, 'custom_stock_entry'):
        pi.custom_stock_entry = stock_entry.name

    # Add items
    for item in items:
        pi.append("items", {
            "item_code": item.item_code,
            "item_name": item.item_name,
            "description": item.description,
            "qty": flt(item.qty),
            "uom": item.uom,
            "stock_uom": item.stock_uom,
            "conversion_factor": item.conversion_factor or 1.0,
            "rate": flt(item.basic_rate) or flt(item.valuation_rate) or 0,
            "warehouse": item.t_warehouse,  # Target warehouse for reporting
        })

    pi.flags.ignore_permissions = True
    pi.flags.ignore_mandatory = True
    pi.insert()

    logger.info("Created Purchase Invoice: %s for Stock Entry: %s", pi.name, stock_entry.name)
    return pi


def _show_success_message(created_docs: List[Dict]) -> None:
    """Show success message with clickable HTML links to created documents.

    Args:
        created_docs: List of dicts with si and pi names
    """
    html_parts = []

    for doc_info in created_docs:
        si_link = f'<a href="/app/sales-invoice/{doc_info["si"]}">{doc_info["si"]}</a>'
        pi_link = f'<a href="/app/purchase-invoice/{doc_info["pi"]}">{doc_info["pi"]}</a>'

        html_parts.append(f"""
        <div style="margin-bottom: 10px;">
            <strong>{doc_info["source"]} → {doc_info["target"]}</strong><br>
            📤 Sales Invoice: {si_link}<br>
            📥 Purchase Invoice: {pi_link}
        </div>
        """)

    message = f"""
    <h4>✅ Inter-Company hujjatlari yaratildi:</h4>
    {''.join(html_parts)}
    <p><em>Iltimos, hujjatlarni tekshirib, submit qiling.</em></p>
    """

    frappe.msgprint(
        message,
        title=_("Inter-Company Transfer"),
        indicator="green",
        is_minimizable=True
    )
