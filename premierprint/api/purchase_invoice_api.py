# Copyright (c) 2024, Premier Print
# For license information, please see license.txt

import frappe
from frappe import _
import json


@frappe.whitelist()
def get_last_purchase_prices(items):
    """
    Fetch last purchase price for a list of items.
    
    Priority:
    1. Last submitted Purchase Receipt Item (most recent actual purchase)
    2. Item Price with buying=1 (fallback)
    
    Args:
        items: JSON string or list of item_codes
        
    Returns:
        dict: {item_code: {"price": float, "source": str}}
    """
    if isinstance(items, str):
        items = json.loads(items)
    
    if not items:
        return {}
    
    result = {}
    
    # 1. First try to get from last Purchase Receipt (most accurate)
    last_pr_prices = frappe.db.sql("""
        SELECT 
            pri.item_code,
            pri.rate as price,
            pr.name as receipt_name,
            pr.posting_date
        FROM `tabPurchase Receipt Item` pri
        INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.item_code IN %(items)s
          AND pr.docstatus = 1
        ORDER BY pr.posting_date DESC, pr.creation DESC
    """, {"items": items}, as_dict=True)
    
    # Store first found price for each item (latest)
    for row in last_pr_prices:
        if row.item_code not in result:
            result[row.item_code] = {
                "price": row.price,
                "source": f"PR ({row.receipt_name})"
            }
    
    # 2. For items not found in PR, try Purchase Invoice
    missing_items = [item for item in items if item not in result]
    
    if missing_items:
        last_pi_prices = frappe.db.sql("""
            SELECT 
                pii.item_code,
                pii.rate as price,
                pi.name as invoice_name
            FROM `tabPurchase Invoice Item` pii
            INNER JOIN `tabPurchase Invoice` pi ON pi.name = pii.parent
            WHERE pii.item_code IN %(items)s
              AND pi.docstatus = 1
            ORDER BY pi.posting_date DESC, pi.creation DESC
        """, {"items": missing_items}, as_dict=True)
        
        for row in last_pi_prices:
            if row.item_code not in result:
                result[row.item_code] = {
                    "price": row.price,
                    "source": f"PI ({row.invoice_name})"
                }
    
    # 3. For still missing items, try Item Price
    still_missing = [item for item in items if item not in result]
    
    if still_missing:
        item_prices = frappe.db.sql("""
            SELECT 
                ip.item_code,
                ip.price_list_rate as price,
                ip.price_list
            FROM `tabItem Price` ip
            WHERE ip.item_code IN %(items)s
              AND ip.buying = 1
            ORDER BY ip.modified DESC
        """, {"items": still_missing}, as_dict=True)
        
        for row in item_prices:
            if row.item_code not in result:
                result[row.item_code] = {
                    "price": row.price,
                    "source": f"Item Price ({row.price_list})"
                }
    
    # 4. For completely new items, mark as new
    for item in items:
        if item not in result:
            result[item] = {
                "price": 0,
                "source": "Yangi (tarix yo'q)"
            }
    
    return result


@frappe.whitelist()
def get_item_last_purchase_rate(item_code):
    """
    Get last purchase rate for a single item.
    """
    result = get_last_purchase_prices([item_code])
    return result.get(item_code, {"price": 0, "source": "Yangi"})
