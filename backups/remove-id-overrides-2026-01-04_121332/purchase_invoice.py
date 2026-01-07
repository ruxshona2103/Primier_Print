"""
Custom Purchase Invoice controller override for auto-increment naming with category
and allowing rate modifications from PO/PR
"""
import frappe
from erpnext.accounts.doctype.purchase_invoice.purchase_invoice import PurchaseInvoice
from premierprint.utils.naming_helper import get_category_from_series, get_item_codes, get_next_id, build_name_with_items


class CustomPurchaseInvoice(PurchaseInvoice):
    """
    Purchase Invoice uchun maxsus controller.

    O'zgarishlar:
    - autoname(): Kategoriya asosida nomlanish (Рpi0000001/23/45/67 formatida)
    - validate(): Rate validatsiyasini o'tkazib yuborish (PO/PR dan narx o'zgartirish uchun)
    - validate_with_previous_doc(): PO/PR bilan bog'liq rate tekshirishni o'tkazib yuborish
    """

    def autoname(self):
        """Format: Рpi0000001/23/45/67"""
        category_code = get_category_from_series(self.naming_series, "pi")
        next_id = get_next_id("Purchase Invoice", category_code)
        base_name = f"{category_code}{next_id}"
        item_codes = get_item_codes(self)
        self.name = build_name_with_items(base_name, item_codes)

    def validate(self):
        """Override validate to allow rate changes from PO/PR"""
        # Skip rate validation for PO/PR linked items
        # This allows users to modify prices via frontend Dialog
        self._skip_rate_validation = True

        # Call parent validate
        super().validate()

    def validate_purchase_receipt_if_update_stock(self):
        """Override to skip rate comparison with Purchase Receipt"""
        # Allow rate modifications - handled via frontend Dialog
        pass

    def validate_with_previous_doc(self):
        """Override to allow rate changes from PO/PR

        Standard ERPNext validates that PI rates match PO/PR rates.
        We override this to allow price modifications via frontend Dialog.
        """
        # Get parent's validation but skip rate validation
        from erpnext.controllers.buying_controller import BuyingController

        # Store original items
        original_items = self.items

        # Temporarily remove items with PO/PR to skip rate validation
        items_with_po_pr = []
        items_without_po_pr = []

        for item in self.items:
            if item.purchase_order or item.purchase_receipt:
                items_with_po_pr.append(item)
            else:
                items_without_po_pr.append(item)

        # Validate only non-PO/PR items
        self.items = items_without_po_pr

        # Call parent validation (won't check rates for PO/PR items)
        try:
            super(PurchaseInvoice, self).validate_with_previous_doc()
        except:
            pass  # Ignore validation errors

        # Restore all items
        self.items = original_items

