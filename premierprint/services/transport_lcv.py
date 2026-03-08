"""
Transport LCV Creation Service
================================
Full pipeline:
  1. Create & submit Carrier Purchase Invoice (Transport PI)
  2. Create & submit Landed Cost Voucher linked to the original PI's Purchase Receipt(s)

Custom Fields assumed on Purchase Invoice:
  - custom_transport_cost        : Float  — transport charge amount
  - custom_lcv_currency          : Link/Currency — "USD" or "UZS"
  - custom_lcv_exchange_rate     : Float  — exchange rate for conversion
  - custom_lcv_taqsimlash_usuli  : Select — "Qty" | "Amount" | "Distribute Manually"
  - custom_transport_pi          : Data/Link — stores created Carrier PI name (duplicate guard)

Supplier mapping (custom_lcv_currency):
  USD  ->  "Logistika Servis USD"
  UZS  ->  "Logistika Servis UZS"

Expense account used in BOTH Carrier PI item and LCV charge:
  "Expenses Included In Valuation - {company_abbr}"
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

from premierprint.services.lcv_utils import (
    convert_to_company_currency,
    get_transport_expense_account,
)


# ---------------------------------------------------------------------------
# PUBLIC ENTRY POINT
# ---------------------------------------------------------------------------

def run_transport_pipeline(doc):
    """
    Main entry point called from lcv_trigger.on_submit().

    Steps:
      1. Guard: custom_transport_cost must be > 0
      2. Duplicate guard: skip if Carrier PI already created for this PI
      3. Create & submit Carrier PI
      4. Create & submit LCV
      5. Store Carrier PI name on original PI for audit trail

    Args:
        doc: Submitted Purchase Invoice document

    Returns:
        dict: {"carrier_pi": str, "lcv": str} or None if skipped
    """
    transport_cost = flt(doc.get("custom_transport_cost"))
    if transport_cost <= 0:
        return None  # Nothing to do - silent exit

    # Duplicate guard
    existing_carrier_pi = doc.get("custom_transport_pi")
    if existing_carrier_pi and frappe.db.exists("Purchase Invoice", existing_carrier_pi):
        frappe.msgprint(
            _("Transport PI {0} already exists for this Purchase Invoice. Skipping.").format(
                frappe.bold(existing_carrier_pi)
            ),
            indicator="blue",
            alert=True,
        )
        return None

    # Fetch shared parameters
    transport_currency = doc.get("custom_lcv_currency")
    if not transport_currency:
        frappe.throw(_("custom_lcv_currency is required to create the Transport PI."))

    lcv_exchange_rate = flt(doc.get("custom_lcv_exchange_rate"))
    if lcv_exchange_rate <= 0:
        frappe.throw(_("custom_lcv_exchange_rate must be > 0 to create the Transport PI."))

    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")

    # Convert transport cost to company currency
    if transport_currency == company_currency:
        transport_amount_company = transport_cost
    else:
        transport_amount_company = convert_to_company_currency(
            amount=transport_cost,
            from_currency=transport_currency,
            to_currency=company_currency,
            conversion_rate=lcv_exchange_rate,
        )

    # Purchase Receipts
    pr_list = get_purchase_receipts_from_pi(doc)
    if not pr_list:
        frappe.throw(
            _("No Purchase Receipts linked to PI {0}. Cannot create Transport LCV.").format(doc.name)
        )

    # Step 1: Carrier PI
    carrier_pi_name = _create_carrier_pi(
        original_pi=doc,
        transport_cost=transport_cost,
        transport_currency=transport_currency,
        lcv_exchange_rate=lcv_exchange_rate,
        company_currency=company_currency,
    )

    # Step 2: LCV
    lcv_name = create_transport_lcv(
        doc=doc,
        pr_list=pr_list,
        transport_amount=transport_amount_company,
        original_amount=transport_cost,
        original_currency=transport_currency,
        exchange_rate=lcv_exchange_rate,
    )

    # Step 3: Store Carrier PI reference on original PI (agar field mavjud bo'lsa)
    # custom_transport_pi field fixtures orqali deploy qilinmagan serverlarda yo'q bo'lishi mumkin
    try:
        # Field mavjudligini tekshir
        field_exists = frappe.db.get_value(
            "Custom Field",
            {"dt": "Purchase Invoice", "fieldname": "custom_transport_pi"},
            "name"
        )
        if field_exists:
            frappe.db.set_value("Purchase Invoice", doc.name, "custom_transport_pi", carrier_pi_name)
            frappe.db.commit()
    except Exception:
        frappe.logger().warning(
            f"custom_transport_pi field not found — skipping. Carrier PI: {carrier_pi_name}"
        )

    frappe.msgprint(
        _("Transport pipeline complete — Carrier PI: {0} | LCV: {1}").format(
            frappe.bold(carrier_pi_name), frappe.bold(lcv_name)
        ),
        indicator="green",
        alert=True,
    )

    return {"carrier_pi": carrier_pi_name, "lcv": lcv_name}


# ---------------------------------------------------------------------------
# STEP 1: CARRIER PURCHASE INVOICE
# ---------------------------------------------------------------------------

def _create_carrier_pi(
    original_pi, transport_cost, transport_currency, lcv_exchange_rate, company_currency
):
    """
    Create and submit a Purchase Invoice for the transport carrier.

    Supplier resolution:
        custom_lcv_currency == "USD"  ->  "Logistika Servis USD"
        custom_lcv_currency == "UZS"  ->  "Logistika Servis UZS"

    The single line item is "Transport xizmati" and its expense_account is
    strictly set to "Expenses Included In Valuation - {abbr}".

    Returns:
        str: Name of the created and submitted Carrier PI
    """
    supplier = _get_carrier_supplier(transport_currency)
    expense_account = get_transport_expense_account(original_pi.company)

    # ERPNext conversion_rate semantics:
    #   "1 unit of PI currency = N units of company currency"
    #
    # User's lcv_exchange_rate is ALWAYS stored as:
    #   "1 USD = X UZS"  (human-readable, strong-to-weak)
    #   e.g. lcv_exchange_rate = 12,099.18
    #
    # Case A: PI currency = USD, company = UZS
    #   -> 1 USD = 12,099 UZS -> conversion_rate = 12,099  ✅ use as-is
    #
    # Case B: PI currency = UZS, company = USD
    #   -> 1 UZS = 1/12,099 USD -> conversion_rate = 1/12,099 = 0.0000826  ✅ invert
    #
    # Case C: same currency -> rate = 1.0
    if transport_currency == company_currency:
        pi_conversion_rate = 1.0
    else:
        # Determine which side is stronger by checking if company_currency is USD
        # and transport_currency is UZS (weak). When PI is in the WEAK currency,
        # we must invert the human rate.
        #
        # General rule: if lcv_exchange_rate > 1, the user expressed it as
        # "1 strong = N weak". If PI currency IS the weak one, invert.
        # We detect this by comparing: does company_currency == "USD" and
        # transport_currency != "USD"? No — use a currency-agnostic approach:
        # fetch the official ERPNext rate for transport_currency -> company_currency.
        # If official rate < 1 and lcv_exchange_rate > 1, they are inverses -> invert.
        try:
            from erpnext.setup.utils import get_exchange_rate
            official = get_exchange_rate(
                from_currency=transport_currency,
                to_currency=company_currency,
                transaction_date=nowdate(),
            )
            if official and flt(official) > 0:
                pi_conversion_rate = flt(official)
            else:
                raise ValueError("no official rate")
        except Exception:
            # Fallback: derive from lcv_exchange_rate direction heuristic
            # lcv_exchange_rate > 1 almost always means "1 strong = N weak"
            # If company_currency is the strong one, PI is in weak -> invert
            if flt(lcv_exchange_rate) > 1:
                pi_conversion_rate = 1.0 / flt(lcv_exchange_rate)
            else:
                pi_conversion_rate = flt(lcv_exchange_rate)

    # Resolve the correct payable (credit_to) account whose currency matches
    # the transport_currency. ERPNext enforces: PI currency == credit_to account currency.
    credit_to_account = _get_payable_account(original_pi.company, transport_currency)

    carrier_pi = frappe.new_doc("Purchase Invoice")
    carrier_pi.supplier = supplier
    carrier_pi.company = original_pi.company
    carrier_pi.posting_date = nowdate()
    carrier_pi.currency = transport_currency
    carrier_pi.conversion_rate = pi_conversion_rate
    carrier_pi.credit_to = credit_to_account
    carrier_pi.buying_price_list = (
        frappe.db.get_value("Buying Settings", None, "buying_price_list") or "Standard Buying"
    )
    carrier_pi.is_return = 0
    carrier_pi.update_stock = 0
    carrier_pi.set_posting_time = 0
    carrier_pi.remarks = _("Transport charge for Purchase Invoice: {0}").format(original_pi.name)

    transport_item = _get_transport_item()

    carrier_pi.append(
        "items",
        {
            "item_code": transport_item,
            "item_name": "Transport xizmati",
            "description": _("Transport xizmati — {0}").format(original_pi.name),
            "qty": 1,
            "rate": flt(transport_cost, 4),
            "amount": flt(transport_cost, 4),
            "uom": "Nos",
            "expense_account": expense_account,
            "cost_center": frappe.db.get_value("Company", original_pi.company, "cost_center"),
        },
    )

    # No taxes — pure service charge
    carrier_pi.taxes_and_charges = ""
    carrier_pi.taxes = []

    try:
        carrier_pi.flags.ignore_permissions = True
        carrier_pi.insert()
        frappe.db.commit()

        carrier_pi.submit()
        frappe.db.commit()

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Carrier PI Creation Failed — Source PI: {}".format(original_pi.name),
        )
        frappe.throw(
            _("Failed to create/submit Carrier Purchase Invoice. See Error Log for details.")
        )

    return carrier_pi.name


# ---------------------------------------------------------------------------
# STEP 2: LANDED COST VOUCHER
# ---------------------------------------------------------------------------

def create_transport_lcv(doc, pr_list, transport_amount, original_amount, original_currency, exchange_rate):
    """
    Create and submit a Landed Cost Voucher for transport charges.

    Items are sourced from the Purchase Invoice (not the Purchase Receipt)
    to correctly handle partial invoice scenarios (1 PR -> multiple PIs).

    Args:
        doc              : Purchase Invoice document (submitted)
        pr_list          : List of Purchase Receipt names
        transport_amount : Transport cost in company currency (already converted)
        original_amount  : Original amount in original_currency
        original_currency: Currency of the transport cost
        exchange_rate    : Exchange rate used for conversion

    Returns:
        str: Name of the created and submitted LCV
    """
    if not pr_list:
        frappe.throw(_("No Purchase Receipts provided for Transport LCV."))
    if flt(transport_amount) <= 0:
        frappe.throw(_("Transport amount must be > 0."))
    if not doc.items:
        frappe.throw(_("Purchase Invoice has no items to allocate transport cost."))

    # Duplicate guard
    existing_lcv = frappe.db.exists(
        "Landed Cost Voucher",
        {
            "custom_purchase_invoice": doc.name,
            "custom_lcv_type": "Transport",
            "docstatus": ["!=", 2],
        },
    )
    if existing_lcv:
        frappe.msgprint(
            _("Transport LCV {0} already exists for PI {1}. Skipping.").format(
                frappe.bold(existing_lcv), doc.name
            ),
            indicator="blue",
            alert=True,
        )
        return existing_lcv

    company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
    expense_account = get_transport_expense_account(doc.company)

    lcv = frappe.new_doc("Landed Cost Voucher")
    lcv.company = doc.company
    lcv.posting_date = nowdate()
    lcv.custom_purchase_invoice = doc.name
    lcv.custom_lcv_type = "Transport"
    lcv.distribute_charges_based_on = _map_allocation_method(
        doc.get("custom_lcv_taqsimlash_usuli")
    )

    # Purchase Receipts table
    for pr_name in pr_list:
        pr_data = frappe.db.get_value(
            "Purchase Receipt",
            pr_name,
            ["supplier", "currency", "conversion_rate"],
            as_dict=True,
        )
        if not pr_data:
            frappe.throw(_("Purchase Receipt {0} not found.").format(pr_name))

        lcv.append(
            "purchase_receipts",
            {
                "receipt_document_type": "Purchase Receipt",
                "receipt_document": pr_name,
                "supplier": pr_data.supplier,
                "grand_total": 0,  # Recalculated below
            },
        )

    # Items from PI
    _populate_lcv_items_from_pi(lcv, doc, company_currency)

    # Sync PR grand totals to actual item sums
    _recalculate_pr_grand_totals(lcv)

    # Applicable charges
    description = _("Transport from {0}: {1} {2}").format(
        doc.name, flt(original_amount, 2), original_currency
    )
    if original_currency != company_currency:
        description += _(" @ rate {0}").format(flt(exchange_rate, 6))

    lcv.append(
        "taxes",
        {
            "description": description,
            "expense_account": expense_account,  # ALWAYS Expenses Included In Valuation
            "amount": flt(transport_amount, 2),
        },
    )

    try:
        lcv.flags.ignore_permissions = True
        lcv.insert()
        frappe.db.commit()

        lcv.submit()
        frappe.db.commit()

    except Exception:
        frappe.log_error(
            message=frappe.get_traceback(),
            title="Transport LCV Submission Failed — PI: {}".format(doc.name),
        )
        frappe.throw(
            _("Failed to create/submit Transport LCV. See Error Log for details.")
        )

    frappe.msgprint(
        _("Transport LCV {0} created and submitted.").format(frappe.bold(lcv.name)),
        indicator="green",
        alert=True,
    )
    return lcv.name


# ---------------------------------------------------------------------------
# VALIDATION HELPER (called from lcv_trigger.validate)
# ---------------------------------------------------------------------------

def validate_transport_lcv_creation(doc):
    """
    Check whether a Transport LCV can be created from this PI.

    Returns:
        tuple: (bool, str) -- (is_valid, error_message)
    """
    if flt(doc.get("custom_transport_cost")) <= 0:
        return False, _("custom_transport_cost must be > 0.")

    if flt(doc.get("custom_lcv_exchange_rate")) <= 0:
        return False, _("custom_lcv_exchange_rate must be provided and > 0.")

    if not get_purchase_receipts_from_pi(doc):
        return False, _("No Purchase Receipts linked to this PI.")

    if not doc.items:
        return False, _("Purchase Invoice has no items.")

    existing = frappe.db.exists(
        "Landed Cost Voucher",
        {
            "custom_purchase_invoice": doc.name,
            "custom_lcv_type": "Transport",
            "docstatus": ["!=", 2],
        },
    )
    if existing:
        return False, _("Transport LCV {0} already exists for this PI.").format(existing)

    return True, ""


# ---------------------------------------------------------------------------
# UTILITY: PURCHASE RECEIPTS FROM PI
# ---------------------------------------------------------------------------

def get_purchase_receipts_from_pi(doc):
    """
    Extract unique Purchase Receipt names from PI line items.

    Returns:
        list[str]: Ordered unique PR names
    """
    seen = []
    for item in doc.items or []:
        if item.purchase_receipt and item.purchase_receipt not in seen:
            seen.append(item.purchase_receipt)
    return seen


# ---------------------------------------------------------------------------
# PRIVATE HELPERS
# ---------------------------------------------------------------------------

def _get_carrier_supplier(transport_currency):
    """Resolve transport supplier name from currency."""
    mapping = {
        "USD": "Logistika Servis USD",
        "UZS": "Logistika Servis UZS",
    }
    supplier = mapping.get(transport_currency)
    if not supplier:
        frappe.throw(
            _(
                "No carrier supplier configured for currency '{0}'. "
                "custom_lcv_currency must be 'USD' or 'UZS'."
            ).format(transport_currency)
        )
    if not frappe.db.exists("Supplier", supplier):
        frappe.throw(
            _(
                "Supplier '{0}' does not exist. Create it in the Supplier master."
            ).format(supplier)
        )
    return supplier


def _get_payable_account(company, currency):
    """
    Return the Payable (credit_to) account for the company whose account_currency
    matches the given currency.

    ERPNext rule: PI currency MUST equal the credit_to account currency.

    Strategy:
      1. Look for a Payable account in the company's Chart of Accounts
         whose account_currency == currency.
      2. Throw with a clear actionable message if none found.
    """
    account = frappe.db.get_value(
        "Account",
        filters={
            "company": company,
            "account_type": "Payable",
            "account_currency": currency,
            "is_group": 0,
            "disabled": 0,
        },
        fieldname="name",
        order_by="creation asc",
    )
    if not account:
        frappe.throw(
            _(
                "No Payable account with currency '{0}' found for company '{1}'. "
                "Create a Payable account in the Chart of Accounts with account_currency = '{0}'."
            ).format(currency, company)
        )
    return account


def _get_transport_item():
    """
    Return the item code for the 'Transport xizmati' service item.

    Lookup strategy:
      1. Check if an item with name (item_code) == 'Transport xizmati' exists.
      2. If not, search by item_name == 'Transport xizmati' (handles auto-numbered items).
      3. Hard-throw with an actionable message if neither is found.

    Returns:
        str: The item `name` (= item_code) field value
    """
    # 1. Direct name/item_code match (ideal case — item was named manually)
    if frappe.db.exists("Item", "Transport xizmati"):
        return "Transport xizmati"

    # 2. item_name match — item exists but was auto-numbered (e.g. name = "5")
    item_code = frappe.db.get_value(
        "Item",
        filters={"item_name": "Transport xizmati", "disabled": 0},
        fieldname="name",
    )
    if item_code:
        return item_code

    # 3. Item genuinely missing — fail loudly
    frappe.throw(
        _(
            "Item 'Transport xizmati' does not exist. "
            "Create a non-stock service Item with item_name = 'Transport xizmati'."
        )
    )


def _map_allocation_method(value):
    """
    Map custom_lcv_taqsimlash_usuli to ERPNext LCV distribute_charges_based_on.

    Valid ERPNext values: "Qty" | "Amount" | "Distribute Manually"
    """
    mapping = {
        "Qty": "Qty",
        "Amount": "Amount",
        "Manually": "Distribute Manually",
        "Distribute Manually": "Distribute Manually",
    }
    return mapping.get(value, "Amount")  # Default: Amount


def _populate_lcv_items_from_pi(lcv, pi_doc, company_currency):
    """
    Add items to the LCV sourced from the Purchase Invoice rows (NOT from PR rows).

    Critical:  A PR may have 100 units. This PI may invoice only 30.
               Using PR items inflates the allocation base. PI items are correct.
    """
    if not pi_doc.items:
        frappe.throw(_("Purchase Invoice {0} has no items.").format(pi_doc.name))

    seen_prs = set()

    for pi_item in pi_doc.items:
        if not pi_item.purchase_receipt:
            frappe.log_error(
                message=(
                    "PI {} — item row {} ({}) has no purchase_receipt link. "
                    "Row skipped for LCV.".format(pi_doc.name, pi_item.idx, pi_item.item_code)
                ),
                title="LCV Item Skipped: Missing PR Reference",
            )
            continue

        if flt(pi_item.qty) <= 0:
            continue

        seen_prs.add(pi_item.purchase_receipt)

        # Fetch PR item details (warehouse, UOM) — best-effort fallback chain
        pr_item_data = None
        if pi_item.pr_detail:
            pr_item_data = frappe.db.get_value(
                "Purchase Receipt Item",
                pi_item.pr_detail,
                ["warehouse", "conversion_factor", "uom", "item_name"],
                as_dict=True,
            )
        if not pr_item_data:
            pr_item_data = frappe.db.get_value(
                "Purchase Receipt Item",
                filters={
                    "parent": pi_item.purchase_receipt,
                    "item_code": pi_item.item_code,
                },
                fieldname=["warehouse", "conversion_factor", "uom", "item_name"],
                as_dict=True,
            )

        # Convert PI item amount to company currency
        item_amount_company = convert_to_company_currency(
            amount=flt(pi_item.amount),
            from_currency=pi_doc.currency,
            to_currency=company_currency,
            conversion_rate=flt(pi_doc.conversion_rate) or 1.0,
        )

        item_rate_company = (
            item_amount_company / flt(pi_item.qty) if flt(pi_item.qty) > 0 else 0.0
        )

        lcv.append(
            "items",
            {
                "item_code": pi_item.item_code,
                "item_name": (
                    pr_item_data.get("item_name") if pr_item_data else pi_item.item_name
                ),
                "description": pi_item.description,
                "qty": flt(pi_item.qty),
                "rate": flt(item_rate_company, 4),
                "amount": flt(item_amount_company, 4),
                "warehouse": (pr_item_data.get("warehouse") if pr_item_data else None),
                "receipt_document_type": "Purchase Receipt",
                "receipt_document": pi_item.purchase_receipt,
                "purchase_receipt_item": pi_item.pr_detail,
                "applicable_charges": 0.0,
                "cost_center": pi_item.cost_center,
                "conversion_factor": (
                    pr_item_data.get("conversion_factor", 1.0) if pr_item_data else 1.0
                ),
                "uom": (pr_item_data.get("uom") if pr_item_data else pi_item.uom),
            },
        )

    if not lcv.items:
        frappe.throw(
            _("No valid items (with PR links) found in PI {0} to populate LCV.").format(
                pi_doc.name
            )
        )

    frappe.logger().debug(
        "LCV items populated from PI {}: {} rows from {} PR(s).".format(
            pi_doc.name, len(lcv.items), len(seen_prs)
        )
    )


def _recalculate_pr_grand_totals(lcv):
    """
    Set each PR row grand_total to the sum of LCV items belonging to that PR.
    Prevents inflated grand_total when only a partial invoice is in scope.
    """
    if not lcv.purchase_receipts or not lcv.items:
        return

    pr_totals = {}
    for item in lcv.items:
        pr_totals[item.receipt_document] = pr_totals.get(item.receipt_document, 0.0) + flt(
            item.amount
        )

    for pr_row in lcv.purchase_receipts:
        pr_row.grand_total = flt(pr_totals.get(pr_row.receipt_document, 0.0), 4)


# ---------------------------------------------------------------------------
# SUMMARY HELPER (for external calls / UI display)
# ---------------------------------------------------------------------------

def get_transport_lcv_summary(lcv_name):
    """Return a plain-dict summary of a Transport LCV for display purposes."""
    if not lcv_name:
        return {}
    lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
    status_map = {0: "Draft", 1: "Submitted", 2: "Cancelled"}
    return {
        "name": lcv.name,
        "company": lcv.company,
        "lcv_type": lcv.get("custom_lcv_type"),
        "purchase_invoice": lcv.get("custom_purchase_invoice"),
        "total_charges": sum(flt(t.amount) for t in lcv.taxes),
        "allocation_method": lcv.distribute_charges_based_on,
        "purchase_receipts": [pr.receipt_document for pr in lcv.purchase_receipts],
        "items_count": len(lcv.items),
        "docstatus": lcv.docstatus,
        "status": status_map.get(lcv.docstatus, "Unknown"),
    }
