"""Custom Stock Ledger Entry for Premier Print.

Override to support inter-company stock transfers by skipping
warehouse-company validation when flag is set.

APPROACH: Monkey patch validate_warehouse_company in the Stock Ledger Entry module.
"""

import frappe
from erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry import StockLedgerEntry

# Import the module where validate_warehouse_company is imported
import erpnext.stock.doctype.stock_ledger_entry.stock_ledger_entry as sle_module

# Store original validate_warehouse_company if exists
try:
    from erpnext.stock.utils import validate_warehouse_company as _original_vwc

    def _patched_validate_warehouse_company(warehouse, company):
        """Patched version that respects ignore flag."""
        if getattr(frappe.flags, 'ignore_validate_warehouse_company', False):
            return  # Skip validation
        return _original_vwc(warehouse, company)

    # Patch it in the Stock Ledger Entry module namespace
    sle_module.validate_warehouse_company = _patched_validate_warehouse_company

except ImportError:
    pass


class CustomStockLedgerEntry(StockLedgerEntry):
    """Extended Stock Ledger Entry with validation bypass support.

    The actual bypass is done via monkey patching above.
    This class just ensures the patch is applied.
    """
    pass
