
import frappe
from frappe.model.document import Document


def before_validate_stock_ledger_entry(doc: Document, method: str = None) -> None:
    """Hook executed before Stock Ledger Entry validation.

    If ignore_validate_warehouse_company flag is set, we patch the
    validate_warehouse_company function in the Stock Ledger Entry module
    to skip validation.

    Args:
        doc: Stock Ledger Entry document
        method: Hook method name (not used)
    """
    # Check if we should bypass warehouse-company validation
    if not getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
        return

    # Apply monkey patch to Stock Ledger Entry module
    try:
        import erpnext.stock.utils as stock_utils
        import erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry as sle_module

        # Store original if not already stored
        if not hasattr(sle_module, '_original_validate_warehouse_company'):
            sle_module._original_validate_warehouse_company = getattr(
                sle_module, 'validate_warehouse_company',
                stock_utils.validate_warehouse_company
            )

        def _patched_validate_warehouse_company(warehouse, company):
            """Patched version that respects ignore flag."""
            if getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
                return  # Skip validation
            return sle_module._original_validate_warehouse_company(warehouse, company)

        # Apply patch
        sle_module.validate_warehouse_company = _patched_validate_warehouse_company

    except Exception as e:
        frappe.log_error(
            f"Failed to patch validate_warehouse_company: {str(e)}",
            "Stock Ledger Entry Patch Error"
        )
