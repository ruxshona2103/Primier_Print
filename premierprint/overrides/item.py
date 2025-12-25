"""
Custom Item controller override for auto-increment naming
"""
import frappe
from erpnext.stock.doctype.item.item import Item


class CustomItem(Item):
    def autoname(self):
        """
        Override ERPNext's autoname to use simple numeric IDs: 1, 2, 3, 4...
        """
        # Get next ID from our custom function
        from premierprint.utils.naming import get_next_item_id

        next_id = get_next_item_id()
        self.item_code = next_id
        self.name = next_id
