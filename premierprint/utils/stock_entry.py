"""Stock Entry utilities for Premier Print.

This module provides:
1. Query functions for Sales Order/Sales Order Item dropdown
2. BOM material explosion logic

Used for: "Услуга по заказу" and "Расход по заказу" stock entry types.
"""

from typing import Dict, List

import frappe
from frappe import _
from frappe.utils import flt


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

    Returns:
        List of tuples: [(name, item_name, item_code, qty, uom), ...]
    """
    sales_order = filters.get("parent") or filters.get("sales_order") if filters else None
    search_txt = f"%{txt}%"

    if not sales_order:
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
def get_bom_materials(sales_order_item: str = None, sales_order_item_id: str = None) -> List[Dict]:
    """Explode BOM and return raw materials for a Sales Order Item.

    Args:
        sales_order_item: Sales Order Item name (ID)
        sales_order_item_id: Alias for sales_order_item (backwards compatibility)

    Returns:
        List of dict with item details
    """
    soi_name = sales_order_item or sales_order_item_id
    
    if not soi_name:
        frappe.throw(_("Sales Order Item is required"))

    # Get Sales Order Item details
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
