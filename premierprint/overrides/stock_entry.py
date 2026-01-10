"""Custom Stock Entry Controller for Premier Print.

This module provides:
1. Validation bypass for inter-company transfers (Перемещение type)
2. Monkey patches validate_warehouse_company to allow cross-company transfers

VALIDATION BYPASS MECHANISM:
The standard ERPNext validates warehouse-company match in:
- erpnext/stock/utils.py -> validate_warehouse_company()

Since ERPNext doesn't check flags, we monkey-patch the function.
"""

import frappe
from frappe import _
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry

# Store reference to original function
import erpnext.stock.utils as stock_utils
_original_validate_warehouse_company = stock_utils.validate_warehouse_company


def _patched_validate_warehouse_company(warehouse, company):
    """Patched version that respects ignore flag.
    
    If frappe.flags.ignore_validate_warehouse_company is True,
    skip the validation entirely.
    """
    if getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
        return
    
    # Call original function
    return _original_validate_warehouse_company(warehouse, company)


# Apply the monkey patch
stock_utils.validate_warehouse_company = _patched_validate_warehouse_company


class CustomStockEntry(StockEntry):
    """Extended Stock Entry with inter-company transfer support.

    The actual inter-company document creation (SI, PI) is handled by
    the on_submit hook in premierprint.utils.stock_entry.on_submit_stock_entry
    """

    def validate(self):
        """Validate Stock Entry with inter-company transfer support.

        For "Перемещение" type:
        - Set flag to skip warehouse-company validation
        - Re-apply monkey patch to ensure it's active
        - Set item-level flags to bypass validation
        - Patch Stock Ledger Entry module
        """
        if self.stock_entry_type == "Перемещение":
            # Re-apply monkey patch (in case it was overridden)
            stock_utils.validate_warehouse_company = _patched_validate_warehouse_company

            # CRITICAL: Also patch Stock Ledger Entry module
            try:
                import erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry as sle_module
                sle_module.validate_warehouse_company = _patched_validate_warehouse_company
            except Exception:
                pass

            # Set global flag to skip validation
            frappe.flags.ignore_validate_warehouse_company = True

            # Set document-level flag
            self.flags.ignore_validate_warehouse_company = True

        try:
            super().validate()
        finally:
            # Clean up flag
            frappe.flags.ignore_validate_warehouse_company = False
            self.flags.ignore_validate_warehouse_company = False

    def validate_warehouse(self):
        """Override warehouse validation for inter-company transfers.

        For "Перемещение" type, skip warehouse-company validation.
        """
        if self.stock_entry_type == "Перемещение":
            # Set flag before calling parent method
            frappe.flags.ignore_validate_warehouse_company = True
            self.flags.ignore_validate_warehouse_company = True

        try:
            super().validate_warehouse()
        finally:
            if self.stock_entry_type == "Перемещение":
                frappe.flags.ignore_validate_warehouse_company = False
                self.flags.ignore_validate_warehouse_company = False

    def validate_warehouse_account(self):
        """Override warehouse account validation for inter-company transfers.

        For "Перемещение" type, skip warehouse account validation.
        Since GL entries won't be created, warehouse accounts are not needed.
        """
        if self.stock_entry_type == "Перемещение":
            # Skip warehouse account validation for inter-company transfers
            return

        # Normal validation for other types
        super().validate_warehouse_account()

    def make_batches(self, warehouse_field):
        """Override to set flag before batch processing."""
        if self.stock_entry_type == "Перемещение":
            frappe.flags.ignore_validate_warehouse_company = True

        try:
            return super().make_batches(warehouse_field)
        finally:
            if self.stock_entry_type == "Перемещение":
                frappe.flags.ignore_validate_warehouse_company = False

    def on_submit(self):
        """Override on_submit to ensure patch is active during stock ledger creation."""
        if self.stock_entry_type == "Перемещение":
            # Re-apply patch before creating stock ledger entries
            stock_utils.validate_warehouse_company = _patched_validate_warehouse_company

            # Patch Stock Ledger Entry module
            try:
                import erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry as sle_module
                sle_module.validate_warehouse_company = _patched_validate_warehouse_company
            except Exception:
                pass

            # Set flag
            frappe.flags.ignore_validate_warehouse_company = True
            self.flags.ignore_validate_warehouse_company = True

        try:
            super().on_submit()
        finally:
            if self.stock_entry_type == "Перемещение":
                frappe.flags.ignore_validate_warehouse_company = False
                self.flags.ignore_validate_warehouse_company = False

    def make_gl_entries(self, gl_entries=None, from_repost=False):
        """Override GL entry creation for inter-company transfers.

        For "Перемещение" type, skip GL entries entirely.
        Accounting will be done via Sales Invoice and Purchase Invoice.
        """
        if self.stock_entry_type == "Перемещение":
            # Skip GL entries for inter-company transfers
            # Sales Invoice and Purchase Invoice will handle accounting
            return

        # Normal GL entry creation for other types
        return super().make_gl_entries(gl_entries, from_repost)

    def get_gl_entries(self, warehouse_account=None):
        """Override to prevent GL entries for inter-company transfers.

        For "Перемещение" type, return empty list.
        """
        if self.stock_entry_type == "Перемещение":
            # No GL entries for inter-company transfers
            return []

        # Normal GL entry generation for other types
        return super().get_gl_entries(warehouse_account)
