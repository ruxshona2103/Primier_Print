"""
Custom Sales Order controller override for auto-increment naming with category
"""
import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder
from premierprint.utils.naming_helper import get_category_from_series, get_item_codes, get_next_id, build_name_with_items


class CustomSalesOrder(SalesOrder):
    def autoname(self):
        """Format: Рso0000001/23/45/67"""
        category_code = get_category_from_series(self.naming_series, "so")
        next_id = get_next_id("Sales Order", category_code)
        base_name = f"{category_code}{next_id}"
        item_codes = get_item_codes(self)
        self.name = build_name_with_items(base_name, item_codes)
