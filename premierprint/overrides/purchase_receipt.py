"""
Custom Purchase Receipt controller override for auto-increment naming with category
"""
import frappe
from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from premierprint.utils.naming_helper import get_category_from_series, get_item_codes, get_next_id, build_name_with_items


class CustomPurchaseReceipt(PurchaseReceipt):
    def autoname(self):
        """
        Override ERPNext's autoname to use format: Рpr0000001/23/45/67
        Р/П/С - Kategoriya (Reklama/Poligrafiya/Suvenir)
        pr - Purchase Receipt
        0000001 - 7 xonali raqam
        /23/45/67 - itemlarning item_code lari
        """
        # Get category from naming_series (Рpr, Пpr, Сpr)
        category_code = get_category_from_series(self.naming_series, "pr")

        # Get next ID
        next_id = get_next_id("Purchase Receipt", category_code)

        # Base name: Рpr0000001
        base_name = f"{category_code}{next_id}"

        # Build name with items
        item_codes = get_item_codes(self)
        self.name = build_name_with_items(base_name, item_codes)

