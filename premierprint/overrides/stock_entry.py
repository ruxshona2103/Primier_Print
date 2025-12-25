"""
Custom Stock Entry controller override for auto-increment naming with category
"""
import frappe
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from premierprint.utils.naming_helper import get_category_from_series, get_item_codes, get_next_id, build_name_with_items


class CustomStockEntry(StockEntry):
    def autoname(self):
        """Format: Рse0000001/23/45/67"""
        category_code = get_category_from_series(self.naming_series, "se")
        next_id = get_next_id("Stock Entry", category_code)
        base_name = f"{category_code}{next_id}"
        item_codes = get_item_codes(self)
        self.name = build_name_with_items(base_name, item_codes)
