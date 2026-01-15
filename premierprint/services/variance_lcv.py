"""
Price Variance LCV Creation Service
Handles creation of Landed Cost Vouchers for Price Differences between Purchase Receipt and Purchase Invoice.

CRITICAL BUG FIXES IMPLEMENTED:
1. Deep Currency Standardization - Converts ALL amounts to company currency before comparison
2. Targeted Distribution - Only applies variance to items that actually changed in price
3. PR Grand Total Correction - Prevents "16,000 Bug" by converting PR amounts properly
4. SRBNB Accounting - Uses correct "Stock Received But Not Billed" account for closing
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate
import json

# Import shared utility functions
from premierprint.services.lcv_utils import convert_to_company_currency, get_stock_received_but_not_billed_account


def create_price_variance_lcv(doc, variance_items):
	"""
	Create a Landed Cost Voucher for Price Variance between PR and PI.
	
	This function implements the "Deep Currency Fix" by:
	1. Converting all PR rates to company currency
	2. Converting all PI rates to company currency
	3. Calculating variance only after standardization
	4. Applying variance ONLY to items that changed
	
	Args:
		doc: Purchase Invoice document
		variance_items: List of items with price variances, each containing:
			{
				'pi_item': PI Item object,
				'pr_item': PR Item dict,
				'variance': {
					'variance_company_currency': float (already calculated variance in company currency)
				}
			}
	
	Returns:
		object: Created LCV document, or None if variance is negligible
	
	Raises:
		frappe.ValidationError: If validation fails
	"""
	
	# ============================================================
	# VALIDATION & SETUP
	# ============================================================
	if not variance_items or len(variance_items) == 0:
		frappe.msgprint(_("No price variance items found"), indicator="yellow")
		return None
	
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	
	# Calculate total variance (already in company currency from caller)
	total_variance = sum(
		flt(item['variance']['variance_company_currency']) 
		for item in variance_items
	)
	
	# CRITICAL: Don't create LCV for negligible amounts (< 0.01 in company currency)
	if abs(total_variance) < 0.01:
		frappe.msgprint(
			_("Price variance is negligible ({0} {1}). No LCV created.").format(
				flt(total_variance, 2), 
				company_currency
			),
			indicator="blue"
		)
		return None
	
	# ============================================================
	# CREATE LCV DOCUMENT
	# ============================================================
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = doc.company
	lcv.posting_date = doc.posting_date or nowdate()
	lcv.custom_purchase_invoice = doc.name
	lcv.custom_lcv_type = "Price Variance"
	
	# CRITICAL: Must use "Distribute Manually" for targeted variance allocation
	lcv.distribute_charges_based_on = "Distribute Manually"
	
	# ============================================================
	# ADD PURCHASE RECEIPTS WITH SMART CURRENCY CONVERSION
	# ============================================================
	# CRITICAL FIX: The "16,000 Bug"
	# Extract unique PR names from variance items
	pr_names = list(set(
		item['pi_item'].purchase_receipt 
		for item in variance_items 
		if item['pi_item'].purchase_receipt
	))
	
	if not pr_names:
		frappe.throw(_("No Purchase Receipts found in variance items"))
	
	for pr_name in pr_names:
		# Get PR document with financial details
		pr_doc = frappe.get_cached_doc("Purchase Receipt", pr_name)
		
		# CRITICAL: Convert PR grand total to company currency
		# This prevents the "16,000 Bug" where UZS amounts appeared as USD
		pr_grand_total_company = convert_to_company_currency(
			amount=pr_doc.grand_total,
			from_currency=pr_doc.currency,
			to_currency=company_currency,
			conversion_rate=pr_doc.conversion_rate or 1.0
		)
		
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pr_name,
			"supplier": pr_doc.supplier,
			"grand_total": pr_grand_total_company  # Use converted amount
		})
	
	# Get items from PRs
	lcv.get_items_from_purchase_receipts()
	
	# ============================================================
	# APPLY TARGETED VARIANCE DISTRIBUTION
	# ============================================================
	# CRITICAL: The "10 Items Logic"
	# Only items that changed price should absorb variance
	# Items 4-10 (unchanged) get applicable_charges = 0.00
	_apply_variance_to_items(lcv, variance_items)
	
	# ============================================================
	# ADD VARIANCE AS TAX CHARGE (SRBNB ACCOUNTING)
	# ============================================================
	# CRITICAL: Must use "Stock Received But Not Billed" account
	# This closes the accounting gap created by the Purchase Invoice
	srbnb_account = get_stock_received_but_not_billed_account(doc.company)
	
	# Build detailed description
	description = _("Price Variance from Purchase Invoice: {0}").format(doc.name)
	description += _("<br>Total Variance: {0} {1}").format(
		flt(total_variance, 2),
		company_currency
	)
	description += _("<br>Items with variance: {0} of {1}").format(
		len(variance_items),
		len(doc.items)
	)
	
	lcv.append("taxes", {
		"description": description,
		"expense_account": srbnb_account,
		"amount": flt(total_variance, 2)
	})
	
	# Add detailed comment for audit trail
	lcv.add_comment(
		"Comment",
		_("Price Variance LCV created from Purchase Invoice: {0}<br>Total Variance: {1} {2}<br>Number of items with variance: {3}").format(
			doc.name,
			flt(total_variance, 2),
			company_currency,
			len(variance_items)
		)
	)
	
	# ============================================================
	# SAVE AND SUBMIT
	# ============================================================
	try:
		lcv.flags.ignore_permissions = True
		lcv.insert()
		frappe.db.commit()
		
		# Auto-submit
		lcv.submit()
		frappe.db.commit()
		
		frappe.msgprint(
			_("Price Variance LCV {0} created and submitted successfully<br>Total Variance: {1} {2}").format(
				frappe.bold(lcv.name),
				flt(total_variance, 2),
				company_currency
			),
			indicator="green",
			alert=True
		)
		
		return lcv
		
	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Price Variance LCV Creation Failed for PI: {doc.name}"
		)
		frappe.throw(
			_("Failed to create Price Variance LCV: {0}").format(str(e))
		)


def calculate_item_variance(pi_item, pr_item, pi_doc, pr_doc, company_currency):
	"""
	Calculate price variance for a single item in company currency.
	
	This implements the "Deep Currency Standardization" fix:
	1. Convert PR item rate to company currency
	2. Convert PI item rate to company currency
	3. Calculate variance only after both are in same currency
	
	Args:
		pi_item: Purchase Invoice Item object
		pr_item: Purchase Receipt Item dict
		pi_doc: Purchase Invoice document
		pr_doc: Purchase Receipt document
		company_currency: Company's default currency
	
	Returns:
		dict: Variance information
			{
				'variance_company_currency': float,
				'pr_rate_company': float,
				'pi_rate_company': float,
				'qty': float,
				'has_variance': bool
			}
	"""
	
	# CRITICAL: Step 1 - Convert PR rate to company currency
	pr_rate_company = convert_to_company_currency(
		amount=flt(pr_item.get('rate')),
		from_currency=pr_doc.currency,
		to_currency=company_currency,
		conversion_rate=pr_doc.conversion_rate or 1.0
	)
	
	# CRITICAL: Step 2 - Convert PI rate to company currency
	pi_rate_company = convert_to_company_currency(
		amount=flt(pi_item.rate),
		from_currency=pi_doc.currency,
		to_currency=company_currency,
		conversion_rate=pi_doc.conversion_rate or 1.0
	)
	
	# CRITICAL: Step 3 - Calculate variance in company currency
	qty = flt(pi_item.qty)
	variance_per_unit = pi_rate_company - pr_rate_company
	total_variance = variance_per_unit * qty
	
	return {
		'variance_company_currency': total_variance,
		'pr_rate_company': pr_rate_company,
		'pi_rate_company': pi_rate_company,
		'variance_per_unit': variance_per_unit,
		'qty': qty,
		'has_variance': abs(total_variance) >= 0.01  # Threshold for significance
	}


def detect_variance_items(doc):
	"""
	Detect all items in PI that have price variance compared to their PR.
	
	This is the entry point that implements the "10 Items Logic":
	- Scans all PI items
	- For each, finds matching PR item
	- Calculates variance using deep currency standardization
	- Returns only items with actual variance
	
	Args:
		doc: Purchase Invoice document
	
	Returns:
		list: List of variance items with structure:
			[
				{
					'pi_item': PI Item object,
					'pr_item': PR Item dict,
					'variance': variance_info dict
				},
				...
			]
	"""
	
	variance_items = []
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	
	for pi_item in doc.items:
		# Skip items without PR reference
		if not pi_item.purchase_receipt or not pi_item.pr_detail:
			continue
		
		# Get matching PR item
		pr_item = _get_matching_pr_item(pi_item)
		if not pr_item:
			continue
		
		# Get PR document for currency conversion
		pr_doc = frappe.get_cached_doc("Purchase Receipt", pi_item.purchase_receipt)
		
		# Calculate variance with deep currency standardization
		variance_info = calculate_item_variance(
			pi_item=pi_item,
			pr_item=pr_item,
			pi_doc=doc,
			pr_doc=pr_doc,
			company_currency=company_currency
		)
		
		# Only include items with actual variance
		if variance_info['has_variance']:
			variance_items.append({
				'pi_item': pi_item,
				'pr_item': pr_item,
				'variance': variance_info
			})
	
	return variance_items


def validate_variance_lcv_creation(doc):
	"""
	Validate if a Price Variance LCV can be created from this Purchase Invoice.
	
	Args:
		doc: Purchase Invoice document
	
	Returns:
		tuple: (bool, str) - (is_valid, error_message)
	"""
	
	# Check if any items have PR references
	has_pr_items = any(item.purchase_receipt for item in doc.items)
	if not has_pr_items:
		return False, _("No Purchase Receipt references found in items")
	
	# Check if variance items exist
	variance_items = detect_variance_items(doc)
	if not variance_items:
		return False, _("No price variance detected between PR and PI")
	
	# Check if Variance LCV already exists
	existing_lcv = frappe.db.exists("Landed Cost Voucher", {
		"custom_purchase_invoice": doc.name,
		"custom_lcv_type": "Price Variance",
		"docstatus": ["!=", 2]  # Not cancelled
	})
	
	if existing_lcv:
		return False, _("Price Variance LCV already exists for this Purchase Invoice: {0}").format(existing_lcv)
	
	return True, ""


# ============================================================
# PRIVATE HELPER FUNCTIONS
# ============================================================

def _apply_variance_to_items(lcv, variance_items):
	"""
	Apply variance amounts to specific LCV items (Manual Distribution).
	
	This implements the "Targeted Distribution" logic:
	- Creates a map of PR Item Name -> Variance Amount
	- Iterates through LCV items
	- If item is in map, applies the variance
	- If item is NOT in map (unchanged), sets applicable_charges = 0.00
	
	Args:
		lcv: LCV document object
		variance_items: List of variance items
	"""
	
	# Build variance map: PR Item Name -> Total Variance
	variance_map = {}
	
	for item in variance_items:
		pr_item_name = item['pr_item']['name']  # PR Detail (child table name)
		variance_amount = flt(item['variance']['variance_company_currency'])
		
		# Accumulate if same PR item appears multiple times (shouldn't happen, but safe)
		if pr_item_name in variance_map:
			variance_map[pr_item_name] += variance_amount
		else:
			variance_map[pr_item_name] = variance_amount
	
	# Apply to LCV items
	for lcv_item in lcv.items:
		# Match by purchase_receipt_item (which is the PR Detail name)
		if lcv_item.purchase_receipt_item in variance_map:
			# Item has variance - apply it
			lcv_item.applicable_charges = flt(variance_map[lcv_item.purchase_receipt_item], 2)
		else:
			# Item unchanged - no variance
			lcv_item.applicable_charges = 0.00


def _get_matching_pr_item(pi_item):
	"""
	Get the matching Purchase Receipt item for a Purchase Invoice item.
	
	Args:
		pi_item: Purchase Invoice Item object
	
	Returns:
		dict: PR Item data, or None if not found
	"""
	
	if not pi_item.pr_detail:
		return None
	
	try:
		pr_item = frappe.db.get_value(
			"Purchase Receipt Item",
			pi_item.pr_detail,
			["name", "rate", "qty", "amount", "item_code", "parent"],
			as_dict=True
		)
		return pr_item
	except Exception as e:
		frappe.log_error(
			message=f"Failed to get PR item {pi_item.pr_detail}: {str(e)}",
			title="PR Item Fetch Error"
		)
		return None


def get_variance_summary(doc):
	"""
	Get a summary of price variances for display purposes.
	
	Args:
		doc: Purchase Invoice document
	
	Returns:
		dict: Summary information
	"""
	
	variance_items = detect_variance_items(doc)
	
	if not variance_items:
		return {
			"has_variance": False,
			"total_variance": 0.0,
			"items_with_variance": 0,
			"total_items": len(doc.items)
		}
	
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	total_variance = sum(flt(item['variance']['variance_company_currency']) for item in variance_items)
	
	return {
		"has_variance": True,
		"total_variance": flt(total_variance, 2),
		"currency": company_currency,
		"items_with_variance": len(variance_items),
		"total_items": len(doc.items),
		"variance_items": [
			{
				"item_code": item['pi_item'].item_code,
				"item_name": item['pi_item'].item_name,
				"pr_rate": flt(item['variance']['pr_rate_company'], 4),
				"pi_rate": flt(item['variance']['pi_rate_company'], 4),
				"variance_per_unit": flt(item['variance']['variance_per_unit'], 4),
				"qty": flt(item['variance']['qty']),
				"total_variance": flt(item['variance']['variance_company_currency'], 2)
			}
			for item in variance_items
		]
	}