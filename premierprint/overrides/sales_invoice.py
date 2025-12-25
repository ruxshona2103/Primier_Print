"""
Custom Sales Invoice controller override for auto-increment naming with category
"""
import frappe
from erpnext.accounts.doctype.sales_invoice.sales_invoice import SalesInvoice
from premierprint.utils.naming_helper import get_category_from_series, get_item_codes, get_next_id, build_name_with_items


class CustomSalesInvoice(SalesInvoice):
    def autoname(self):
        """Format: Рsi0000001/23/45/67"""
        category_code = get_category_from_series(self.naming_series, "si")
        next_id = get_next_id("Sales Invoice", category_code)
        base_name = f"{category_code}{next_id}"
        item_codes = get_item_codes(self)
        self.name = build_name_with_items(base_name, item_codes)
