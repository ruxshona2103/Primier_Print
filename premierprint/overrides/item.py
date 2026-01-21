"""
Custom Item controller override for auto-increment naming
"""
import frappe
from erpnext.stock.doctype.item.item import Item


class CustomItem(Item):
    def validate(self):
        """
        Set item_code before validation if not set
        """
        # If item_code is empty or has temporary value, set it
        if not self.item_code or self.item_code.startswith("new-item") or self.item_code.startswith("ITEM-"):
            from premierprint.utils.naming import get_next_item_id
            next_id = get_next_item_id()
            self.item_code = next_id

        super(CustomItem, self).validate()

    def autoname(self):
        """
        Override ERPNext's autoname to use simple numeric IDs: 1, 2, 3, 4...
        """
        if not self.item_code or self.item_code.startswith("STO-ITEM"):
            # Use centralized logic
            from premierprint.utils.naming import autoname_item
            autoname_item(self, None)

        self.name = self.item_code
