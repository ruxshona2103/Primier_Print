"""
Landed Cost Voucher Auto Creation Module for Purchase Invoice

This module provides validation and automation for LCV creation.
Previously, price verification was enforced at server level.
Now, price verification is handled entirely in the frontend via Dialog.
"""

import frappe
from frappe import _


def validate_price_verification(doc, method=None):
    """
    Price verification validation (removed).

    Previously, this function blocked submission if prices weren't verified.
    Now, frontend Dialog handles price verification interactively.
    Server-side blocking is removed for better UX.

    Args:
        doc: Purchase Invoice document
        method: Hook method name (not used)
    """
    # Frontend Dialog now handles all price verification
    # No server-side blocking needed
    pass
