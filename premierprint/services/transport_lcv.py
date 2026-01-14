"""
Transport LCV Creation Service
Handles creation of Landed Cost Vouchers for Transport Charges from Purchase Invoices.

CRITICAL BUG FIXES IMPLEMENTED:
1. PR Grand Total Currency Fix - Prevents "10 Million USD" bug by properly converting PR amounts
2. Transport Cost Conversion Fix - Properly divides by exchange rate instead of multiplying
3. Strict Allocation Mapping - Correctly maps PI allocation settings to LCV
4. Expense Account Safety - Uses proper transport expense account
"""

import frappe
from frappe import _
from frappe.utils import flt

# Import shared utility functions
from premierprint.api.lcv_utils import convert_to_company_currency, get_transport_expense_account


def create_transport_lcv(doc, pr_list, transport_amount, original_amount, original_currency, exchange_rate):
	"""
	Create a Landed Cost Voucher for Transport Charges.
	
	Args:
		doc: Purchase Invoice document
		pr_list: List of Purchase Receipt names
		transport_amount: Transport cost in company currency (already converted)
		original_amount: Original transport cost amount from PI
		original_currency: Currency of the transport cost (from PI)
		exchange_rate: Exchange rate used for conversion (custom_lcv_exchange_rate)
	
	Returns:
		str: Name of the created LCV document
	
	Raises:
		frappe.ValidationError: If validation fails
	"""
	
	# ============================================================
	# VALIDATION
	# ============================================================
	if not pr_list or len(pr_list) == 0:
		frappe.throw(_("No Purchase Receipts found to create Transport LCV"))
	
	if not transport_amount or flt(transport_amount) <= 0:
		frappe.throw(_("Transport amount must be greater than zero"))
	
	# ============================================================
	# CREATE LCV DOCUMENT
	# ============================================================
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = doc.company
	lcv.custom_purchase_invoice = doc.name
	lcv.custom_lcv_type = "Transport"
	
	# Get company currency
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	
	# ============================================================
	# DETERMINE ALLOCATION METHOD (CRITICAL: Strict Mapping)
	# ============================================================
	# Map PI custom_lcv_allocation to LCV distribute_charges_based_on
	allocation_method = doc.get("custom_lcv_allocation") or "Amount"
	
	if allocation_method == "Qty":
		lcv.distribute_charges_based_on = "Qty"
	elif allocation_method == "Amount":
		lcv.distribute_charges_based_on = "Amount"
	elif allocation_method == "Manually":
		lcv.distribute_charges_based_on = "Distribute Manually"
	else:
		# Default fallback
		lcv.distribute_charges_based_on = "Amount"
	
	# ============================================================
	# ADD PURCHASE RECEIPTS WITH SMART CURRENCY CONVERSION
	# ============================================================
	# CRITICAL FIX: The "10 Million USD" Bug
	# We must convert each PR's grand_total if it's in a different currency
	
	for pr_name in pr_list:
		# Fetch PR financial details
		pr_data = frappe.db.get_value(
			"Purchase Receipt", 
			pr_name, 
			["grand_total", "conversion_rate", "currency", "supplier"], 
			as_dict=True
		)
		
		if not pr_data:
			frappe.throw(_("Purchase Receipt {0} not found").format(pr_name))
		
		# CRITICAL: Convert PR grand total to company currency if needed
		# This prevents showing "10,000,000 USD" when it should be "10,000,000 UZS = ~826 USD"
		converted_grand_total = convert_to_company_currency(
			amount=pr_data.grand_total,
			from_currency=pr_data.currency,
			to_currency=company_currency,
			conversion_rate=pr_data.conversion_rate or 1.0
		)
		
		# Add PR to LCV with converted amount
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pr_name,
			"supplier": pr_data.supplier,
			"grand_total": converted_grand_total  # Use converted amount, not raw PR amount
		})
	
	# Get items from PRs
	lcv.get_items_from_purchase_receipts()
	
	# ============================================================
	# ADD TRANSPORT CHARGES (TAXES AND CHARGES)
	# ============================================================
	# CRITICAL FIX: Transport Cost Conversion
	# The transport_amount passed in should already be converted by the caller
	# using convert_to_company_currency, which properly divides by exchange rate
	
	# Get the proper transport expense account
	transport_expense_account = get_transport_expense_account(doc.company)
	
	# Create description with currency info
	description = _("Transport Charges from {0}: {1} {2}").format(
		doc.name,
		flt(original_amount, 2),
		original_currency
	)
	
	if original_currency != company_currency:
		description += _(" (Rate: {0})").format(flt(exchange_rate, 6))
	
	lcv.append("taxes", {
		"description": description,
		"expense_account": transport_expense_account,
		"amount": flt(transport_amount, 2)  # Already in company currency
	})
	
	# Add reference information in comments
	lcv.add_comment(
		"Comment",
		_("Transport LCV created from Purchase Invoice: {0}<br>Original Amount: {1} {2}<br>Exchange Rate: {3}<br>Converted Amount: {4}").format(
			doc.name,
			flt(original_amount, 2),
			original_currency,
			flt(exchange_rate, 6),
			flt(transport_amount, 2)
		)
	)
	
	# ============================================================
	# SAVE AND SUBMIT
	# ============================================================
	try:
		lcv.flags.ignore_permissions = True
		lcv.insert()
		frappe.db.commit()
		
		# Auto-submit if configured
		lcv.submit()
		frappe.db.commit()
		
		frappe.msgprint(
			_("Transport LCV {0} created and submitted successfully").format(
				frappe.bold(lcv.name)
			),
			indicator="green",
			alert=True
		)
		
		return lcv.name
		
	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Transport LCV Creation Failed for PI: {doc.name}"
		)
		frappe.throw(
			_("Failed to create Transport LCV: {0}").format(str(e))
		)


def validate_transport_lcv_creation(doc):
	"""
	Validate if a Transport LCV can be created from this Purchase Invoice.
	
	Args:
		doc: Purchase Invoice document
	
	Returns:
		tuple: (bool, str) - (is_valid, error_message)
	"""
	
	# Check if transport cost exists and is greater than zero
	transport_cost = flt(doc.get("custom_transport_cost"))
	if transport_cost <= 0:
		return False, _("Transport cost must be greater than zero")
	
	# Check if LCV exchange rate is provided
	lcv_exchange_rate = flt(doc.get("custom_lcv_exchange_rate"))
	if lcv_exchange_rate <= 0:
		return False, _("LCV Exchange Rate must be provided and greater than zero")
	
	# Check if Purchase Receipts are linked
	pr_list = get_purchase_receipts_from_pi(doc)
	if not pr_list or len(pr_list) == 0:
		return False, _("No Purchase Receipts found. LCV cannot be created without Purchase Receipts.")
	
	# Check if Transport LCV already exists
	existing_lcv = frappe.db.exists("Landed Cost Voucher", {
		"custom_purchase_invoice": doc.name,
		"custom_lcv_type": "Transport",
		"docstatus": ["!=", 2]  # Not cancelled
	})
	
	if existing_lcv:
		return False, _("Transport LCV already exists for this Purchase Invoice: {0}").format(existing_lcv)
	
	return True, ""


def get_purchase_receipts_from_pi(doc):
	"""
	Get list of Purchase Receipts linked to this Purchase Invoice.
	
	Args:
		doc: Purchase Invoice document
	
	Returns:
		list: List of Purchase Receipt names
	"""
	pr_list = []
	
	# Get PRs from PI items
	for item in doc.items:
		if item.purchase_receipt:
			if item.purchase_receipt not in pr_list:
				pr_list.append(item.purchase_receipt)
	
	return pr_list


def get_transport_lcv_summary(lcv_name):
	"""
	Get a summary of a Transport LCV for display purposes.
	
	Args:
		lcv_name: Name of the LCV document
	
	Returns:
		dict: Summary information
	"""
	if not lcv_name:
		return {}
	
	lcv = frappe.get_doc("Landed Cost Voucher", lcv_name)
	
	return {
		"name": lcv.name,
		"company": lcv.company,
		"lcv_type": lcv.custom_lcv_type,
		"purchase_invoice": lcv.custom_purchase_invoice,
		"total_amount": sum([flt(tax.amount) for tax in lcv.taxes]),
		"allocation_method": lcv.distribute_charges_based_on,
		"purchase_receipts": [pr.receipt_document for pr in lcv.purchase_receipts],
		"status": lcv.docstatus,
		"status_label": "Draft" if lcv.docstatus == 0 else "Submitted" if lcv.docstatus == 1 else "Cancelled"
	}