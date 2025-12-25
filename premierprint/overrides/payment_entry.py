"""
Custom Payment Entry controller override for auto-increment naming with category
"""
import frappe
from erpnext.accounts.doctype.payment_entry.payment_entry import PaymentEntry
from premierprint.utils.naming_helper import get_category_from_series, get_next_id


class CustomPaymentEntry(PaymentEntry):
    def autoname(self):
        """Format: Рpe0000001 (no items)"""
        category_code = get_category_from_series(self.naming_series, "pe")
        next_id = get_next_id("Payment Entry", category_code)
        self.name = f"{category_code}{next_id}"
