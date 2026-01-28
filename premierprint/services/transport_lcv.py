"""
Transport LCV Creation Service - OPTIMIZED VERSION
Handles creation of Landed Cost Vouchers for Transport Charges from Purchase Invoices.

CRITICAL FIXES:
1. ✅ PI-Based Item Allocation - Uses PI item qty, not PR qty
2. ✅ Partial Invoice Support - Handles 1 PR → Multiple PIs correctly
3. ✅ Currency Conversion - Proper exchange rate handling
4. ✅ Smart Grand Total Calculation - Calculates from actual PI items

ARCHITECTURE:
- Uses PI items as source of truth (not PR items)
- Correctly allocates transport only to items in current PI
- Handles edge cases: partial invoices, multiple PRs, mixed currencies
"""

import frappe
from frappe import _
from frappe.utils import flt

# Import shared utility functions
from premierprint.services.lcv_utils import convert_to_company_currency, get_transport_expense_account


def create_transport_lcv(doc, pr_list, transport_amount, original_amount, original_currency, exchange_rate):
	"""
	Create a Landed Cost Voucher for Transport Charges.
	
	CRITICAL: Uses PI items (not PR items) to ensure correct qty allocation
	
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
	
	# Validate PI has items
	if not doc.items or len(doc.items) == 0:
		frappe.throw(_("Purchase Invoice has no items to allocate transport cost"))
	
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
	# ADD PURCHASE RECEIPTS (FOR REFERENCE ONLY)
	# ============================================================
	# Note: We add PRs to satisfy LCV structure requirements,
	# but the actual items will be populated from PI, not PR
	
	for pr_name in pr_list:
		# Fetch PR basic details
		pr_data = frappe.db.get_value(
			"Purchase Receipt", 
			pr_name, 
			["supplier", "currency", "conversion_rate"], 
			as_dict=True
		)
		
		if not pr_data:
			frappe.throw(_("Purchase Receipt {0} not found").format(pr_name))
		
		# Add PR to LCV (grand_total will be calculated from items)
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pr_name,
			"supplier": pr_data.supplier,
			"grand_total": 0  # Will be calculated from actual PI items
		})
	
	# ============================================================
	# ADD ITEMS FROM PURCHASE INVOICE (NOT FROM PR!)
	# ============================================================
	# CRITICAL FIX: Use PI items with PI quantities, not PR items
	# This ensures transport cost is allocated only to items in current PI
	
	_populate_lcv_items_from_pi(lcv, doc, company_currency)
	
	# ============================================================
	# RECALCULATE PR GRAND TOTALS FROM ACTUAL ITEMS
	# ============================================================
	_recalculate_pr_grand_totals(lcv)
	
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
		_("Transport LCV created from Purchase Invoice: {0}<br>Original Amount: {1} {2}<br>Exchange Rate: {3}<br>Converted Amount: {4}<br>Items Count: {5}").format(
			doc.name,
			flt(original_amount, 2),
			original_currency,
			flt(exchange_rate, 6),
			flt(transport_amount, 2),
			len(doc.items)
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


def _populate_lcv_items_from_pi(lcv, pi_doc, company_currency):
	"""
	Populate LCV items from Purchase Invoice items (NOT from PR items).
	
	This is the CORE FIX for partial invoice support:
	- Uses PI item qty (e.g., 30 or 70)
	- Not PR item qty (e.g., 100)
	- Converts amounts to company currency
	- Maintains correct item-to-PR mapping
	
	Args:
		lcv: Landed Cost Voucher document (being built)
		pi_doc: Purchase Invoice document
		company_currency: Company's default currency
	"""
	
	if not pi_doc.items:
		frappe.throw(_("Purchase Invoice has no items"))
	
	# Track PRs we've seen (for validation)
	seen_prs = set()
	
	for pi_item in pi_doc.items:
		# ============================================================
		# VALIDATION: Skip invalid items
		# ============================================================
		
		# Must have purchase receipt reference
		if not pi_item.purchase_receipt:
			frappe.log_error(
				message=f"PI Item {pi_item.item_code} (row {pi_item.idx}) has no purchase_receipt reference",
				title=f"LCV Item Skipped: {pi_doc.name}"
			)
			continue
		
		# Must have qty > 0
		if flt(pi_item.qty) <= 0:
			continue
		
		# Track which PRs are being used
		seen_prs.add(pi_item.purchase_receipt)
		
		# ============================================================
		# GET PR ITEM DETAILS FOR REFERENCE
		# ============================================================
		# We need PR item details for warehouse, conversion factor, etc.
		
		pr_item_data = None
		if pi_item.pr_detail:  # This is the PR item row name
			pr_item_data = frappe.db.get_value(
				"Purchase Receipt Item",
				pi_item.pr_detail,
				["warehouse", "conversion_factor", "uom", "item_name"],
				as_dict=True
			)
		
		if not pr_item_data:
			# Fallback: try to find by item_code and purchase_receipt
			pr_item_data = frappe.db.get_value(
				"Purchase Receipt Item",
				filters={
					"parent": pi_item.purchase_receipt,
					"item_code": pi_item.item_code
				},
				fieldname=["warehouse", "conversion_factor", "uom", "item_name"],
				as_dict=True
			)
		
		# ============================================================
		# CALCULATE ITEM AMOUNT IN COMPANY CURRENCY
		# ============================================================
		# CRITICAL: Convert PI item amount to company currency
		# This prevents "10 Million USD" bug
		
		item_amount = flt(pi_item.amount)  # PI item amount in PI currency
		
		# Convert to company currency if needed
		item_amount_company = convert_to_company_currency(
			amount=item_amount,
			from_currency=pi_doc.currency,
			to_currency=company_currency,
			conversion_rate=flt(pi_doc.conversion_rate) or 1.0
		)
		
		# Calculate rate in company currency
		item_rate_company = item_amount_company / flt(pi_item.qty) if flt(pi_item.qty) > 0 else 0
		
		# ============================================================
		# ADD ITEM TO LCV
		# ============================================================
		lcv.append("items", {
			"item_code": pi_item.item_code,
			"item_name": pr_item_data.get("item_name") if pr_item_data else pi_item.item_name,
			"description": pi_item.description,
			"qty": flt(pi_item.qty),  # ✅ USE PI QTY, NOT PR QTY
			"rate": flt(item_rate_company, 2),  # In company currency
			"amount": flt(item_amount_company, 2),  # In company currency
			"warehouse": pr_item_data.get("warehouse") if pr_item_data else None,
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pi_item.purchase_receipt,
			"purchase_receipt_item": pi_item.pr_detail,  # Link to PR item row
			"applicable_charges": 0.0,  # Will be calculated by LCV logic
			"cost_center": pi_item.cost_center,
			"conversion_factor": pr_item_data.get("conversion_factor", 1.0) if pr_item_data else 1.0,
			"uom": pr_item_data.get("uom") if pr_item_data else pi_item.uom
		})
	
	# ============================================================
	# VALIDATION: Check if we have items
	# ============================================================
	if not lcv.items or len(lcv.items) == 0:
		frappe.throw(_("No valid items found in Purchase Invoice to create LCV"))
	
	# Log summary for debugging
	frappe.logger().debug(
		f"LCV Items populated from PI {pi_doc.name}: "
		f"{len(lcv.items)} items from {len(seen_prs)} PRs"
	)


def _recalculate_pr_grand_totals(lcv):
	"""
	Recalculate Purchase Receipt grand_total values based on actual LCV items.
	
	This ensures PR grand_total in LCV matches the sum of items from that PR,
	not the full PR grand_total (which may include items not in current PI).
	
	Args:
		lcv: Landed Cost Voucher document
	"""
	
	if not lcv.purchase_receipts or not lcv.items:
		return
	
	# Calculate total amount per PR from LCV items
	pr_totals = {}
	
	for item in lcv.items:
		pr_name = item.receipt_document
		item_amount = flt(item.amount)
		
		if pr_name not in pr_totals:
			pr_totals[pr_name] = 0.0
		
		pr_totals[pr_name] += item_amount
	
	# Update PR grand_total values
	for pr_row in lcv.purchase_receipts:
		pr_name = pr_row.receipt_document
		
		if pr_name in pr_totals:
			pr_row.grand_total = flt(pr_totals[pr_name], 2)
		else:
			# This PR has no items in current LCV (shouldn't happen, but handle it)
			pr_row.grand_total = 0.0
	
	# Log for debugging
	frappe.logger().debug(
		f"LCV PR Totals recalculated: {pr_totals}"
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
	
	# Check if PI has items
	if not doc.items or len(doc.items) == 0:
		return False, _("Purchase Invoice has no items")
	
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
		list: List of Purchase Receipt names (unique)
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
		"items_count": len(lcv.items),
		"status": lcv.docstatus,
		"status_label": "Draft" if lcv.docstatus == 0 else "Submitted" if lcv.docstatus == 1 else "Cancelled"
	}