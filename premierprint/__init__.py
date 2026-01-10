__version__ = "0.0.1"

# Monkey patch ERPNext validate_warehouse_company to support inter-company transfers
# This patch is applied at app initialization time

def _apply_inter_company_patch():
    """Apply monkey patch to allow inter-company stock transfers.

    ERPNext's validate_warehouse_company() doesn't support skipping validation.
    We patch it to check frappe.flags.ignore_validate_warehouse_company.

    We patch it in multiple places:
    1. erpnext.stock.utils module
    2. Stock Ledger Entry module (where it's imported)
    """
    try:
        import frappe
        import erpnext.stock.utils as stock_utils

        # Store original function
        _original_validate_warehouse_company = stock_utils.validate_warehouse_company

        def _patched_validate_warehouse_company(warehouse, company):
            """Patched version that respects ignore flag."""
            if getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
                return  # Skip validation for inter-company transfers
            return _original_validate_warehouse_company(warehouse, company)

        # Apply patch to stock.utils module
        stock_utils.validate_warehouse_company = _patched_validate_warehouse_company

        # ALSO patch it in Stock Ledger Entry module
        try:
            import erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry as sle_module
            sle_module.validate_warehouse_company = _patched_validate_warehouse_company
        except Exception:
            pass

    except Exception:
        # Silently fail if erpnext is not available yet
        pass


# Apply patch on module load
_apply_inter_company_patch()
