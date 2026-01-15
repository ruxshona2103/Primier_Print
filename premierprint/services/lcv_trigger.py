"""
LCV Trigger - Purchase Invoice Event Orchestrator
This is the CONTROLLER/ORCHESTRATOR for all LCV-related logic.

ARCHITECTURE:
- Connected to hooks.py as the single entry point
- Routes Purchase Invoice events to specialized modules
- Delegates ALL business logic to service modules
- Contains NO calculation logic (math delegated to lcv_utils)

EVENT FLOW:
1. validate() -> Auto-fill transport from PO
2. on_submit() -> Create Transport LCV and/or Variance LCV
3. on_cancel() -> Cancel linked LCVs

CRITICAL RULES:
- Never perform currency conversions here (use lcv_utils)
- Never create LCV documents here (use transport_lcv/variance_lcv)
- Always use error handling to avoid blocking PI submission
- Log all errors for audit trail
"""

import frappe
from frappe import _
from frappe.utils import flt

# Import utility functions (The Brain)
from premierprint.services.lcv_utils import convert_to_company_currency

# Import specialized service modules
from premierprint.services.transport_lcv import (
	create_transport_lcv,
	validate_transport_lcv_creation,
	get_purchase_receipts_from_pi
)
from premierprint.services.variance_lcv import (
	create_price_variance_lcv,
	detect_variance_items,
	validate_variance_lcv_creation
)


def validate(doc, method):
	"""
	Purchase Invoice Validate Hook
	
	Purpose: Auto-fill transport details from Purchase Order
	
	Args:
		doc: Purchase Invoice document
		method: Hook method name
	"""
	
	# Auto-fill transport cost from PO if not already set
	try:
		_auto_fill_transport_from_po(doc, method)
	except Exception as e:
		# Don't block validation - just log the error
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Transport Auto-Fill Failed for PI: {doc.name}"
		)
		# Optionally notify user
		frappe.msgprint(
			_("Could not auto-fill transport details from Purchase Order: {0}").format(str(e)),
			indicator="orange",
			alert=True
		)


def on_submit(doc, method):
	"""
	Purchase Invoice On Submit Hook
	
	Purpose: Create Landed Cost Vouchers for Transport and/or Price Variance
	
	Args:
		doc: Purchase Invoice document
		method: Hook method name
	"""
	
	# ============================================================
	# LOGIC A: CREATE TRANSPORT LCV
	# ============================================================
	try:
		_handle_transport_lcv_creation(doc)
	except Exception as e:
		# Log error but don't block PI submission
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Transport LCV Creation Failed for PI: {doc.name}"
		)
		frappe.msgprint(
			_("Transport LCV creation failed: {0}<br>Purchase Invoice submitted successfully, but please create LCV manually.").format(str(e)),
			indicator="orange",
			alert=True
		)
	
	# ============================================================
	# LOGIC B: CREATE PRICE VARIANCE LCV
	# ============================================================
	try:
		_handle_variance_lcv_creation(doc)
	except Exception as e:
		# Log error but don't block PI submission
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Price Variance LCV Creation Failed for PI: {doc.name}"
		)
		frappe.msgprint(
			_("Price Variance LCV creation failed: {0}<br>Purchase Invoice submitted successfully, but please create LCV manually.").format(str(e)),
			indicator="orange",
			alert=True
		)


def on_cancel(doc, method):
	"""
	Purchase Invoice On Cancel Hook
	
	Purpose: Cancel all linked Landed Cost Vouchers
	
	Args:
		doc: Purchase Invoice document
		method: Hook method name
	"""
	
	try:
		_cancel_linked_lcvs(doc, method)
	except Exception as e:
		# Log error
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"LCV Cancellation Failed for PI: {doc.name}"
		)
		frappe.msgprint(
			_("Could not cancel linked LCVs automatically: {0}<br>Please cancel them manually.").format(str(e)),
			indicator="orange",
			alert=True
		)


# ============================================================
# PRIVATE ORCHESTRATION FUNCTIONS
# ============================================================

def _handle_transport_lcv_creation(doc):
	"""
	Handle Transport LCV creation logic.
	
	CRITICAL STEPS:
	1. Validate transport cost exists
	2. Convert transport cost to company currency (using lcv_utils)
	3. Get PR list
	4. Call transport_lcv.create_transport_lcv with converted amount
	
	Args:
		doc: Purchase Invoice document
	"""
	
	# Check if transport cost exists
	transport_cost = flt(doc.get("custom_transport_cost"))
	if transport_cost <= 0:
		# No transport cost - skip silently
		return
	
	# Validate if transport LCV can be created
	is_valid, error_msg = validate_transport_lcv_creation(doc)
	if not is_valid:
		frappe.msgprint(
			_("Transport LCV not created: {0}").format(error_msg),
			indicator="blue",
			alert=True
		)
		return
	
	# Get Purchase Receipts
	pr_list = get_purchase_receipts_from_pi(doc)
	if not pr_list:
		frappe.msgprint(
			_("No Purchase Receipts found. Transport LCV cannot be created."),
			indicator="orange",
			alert=True
		)
		return
	
	# Get currencies and exchange rate
	transport_currency = doc.currency  # Usually same as PI currency
	lcv_exchange_rate = flt(doc.get("custom_lcv_exchange_rate"))
	
	if lcv_exchange_rate <= 0:
		frappe.msgprint(
			_("LCV Exchange Rate is required to create Transport LCV"),
			indicator="orange",
			alert=True
		)
		return
	
	# CRITICAL: Convert transport cost to company currency
	# This is where we prevent the "Multiplier Bug"
	company_currency = frappe.get_cached_value("Company", doc.company, "default_currency")
	
	transport_amount_company = convert_to_company_currency(
		amount=transport_cost,
		from_currency=transport_currency,
		to_currency=company_currency,
		conversion_rate=lcv_exchange_rate
	)
	
	# Create Transport LCV
	lcv_name = create_transport_lcv(
		doc=doc,
		pr_list=pr_list,
		transport_amount=transport_amount_company,  # Already converted
		original_amount=transport_cost,
		original_currency=transport_currency,
		exchange_rate=lcv_exchange_rate
	)
	
	if lcv_name:
		# Success message already shown by create_transport_lcv
		pass


def _handle_variance_lcv_creation(doc):
	"""
	Handle Price Variance LCV creation logic.
	
	STEPS:
	1. Detect variance items (using variance_lcv module)
	2. Validate if variance LCV should be created
	3. Call variance_lcv.create_price_variance_lcv
	
	Args:
		doc: Purchase Invoice document
	"""
	
	# Detect items with price variance
	variance_items = detect_variance_items(doc)
	
	if not variance_items:
		# No variance detected - skip silently
		return
	
	# Validate if variance LCV can be created
	is_valid, error_msg = validate_variance_lcv_creation(doc)
	if not is_valid:
		frappe.msgprint(
			_("Price Variance LCV not created: {0}").format(error_msg),
			indicator="blue",
			alert=True
		)
		return
	
	# Create Price Variance LCV
	lcv_doc = create_price_variance_lcv(doc, variance_items)
	
	if lcv_doc:
		# Success message already shown by create_price_variance_lcv
		pass


def _cancel_linked_lcvs(doc, method):
	"""
	Cancel all Landed Cost Vouchers linked to this Purchase Invoice.
	
	Args:
		doc: Purchase Invoice document
		method: Hook method name
	"""
	
	# Find all LCVs linked to this PI
	linked_lcvs = frappe.get_all(
		"Landed Cost Voucher",
		filters={
			"custom_purchase_invoice": doc.name,
			"docstatus": 1  # Only submitted LCVs
		},
		fields=["name", "custom_lcv_type"]
	)
	
	if not linked_lcvs:
		# No linked LCVs - nothing to cancel
		return
	
	cancelled_count = 0
	failed_cancellations = []
	
	for lcv_info in linked_lcvs:
		try:
			lcv_doc = frappe.get_doc("Landed Cost Voucher", lcv_info.name)
			lcv_doc.flags.ignore_permissions = True
			lcv_doc.cancel()
			frappe.db.commit()
			cancelled_count += 1
		except Exception as e:
			failed_cancellations.append({
				"name": lcv_info.name,
				"type": lcv_info.custom_lcv_type,
				"error": str(e)
			})
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"LCV Cancellation Failed: {lcv_info.name}"
			)
	
	# Notify user
	if cancelled_count > 0:
		frappe.msgprint(
			_("Successfully cancelled {0} linked LCV(s)").format(cancelled_count),
			indicator="green",
			alert=True
		)
	
	if failed_cancellations:
		error_details = "<br>".join([
			f"- {item['name']} ({item['type']}): {item['error']}" 
			for item in failed_cancellations
		])
		frappe.msgprint(
			_("Failed to cancel {0} LCV(s):<br>{1}").format(
				len(failed_cancellations),
				error_details
			),
			indicator="red",
			alert=True
		)


def _auto_fill_transport_from_po(doc, method):
	"""
	Auto-fill transport cost and exchange rate from linked Purchase Order.
	
	Logic:
	- Looks for custom_transport_cost and custom_lcv_exchange_rate on PO
	- Fills them into PI if PI fields are empty
	- Only runs during validation, before save
	
	Args:
		doc: Purchase Invoice document
		method: Hook method name
	"""
	
	# Skip if transport cost already set
	if flt(doc.get("custom_transport_cost")) > 0:
		return
	
	# Find linked Purchase Orders from items
	po_list = []
	for item in doc.items:
		if item.purchase_order and item.purchase_order not in po_list:
			po_list.append(item.purchase_order)
	
	if not po_list:
		# No PO linked - nothing to auto-fill
		return
	
	# If multiple POs, use the first one (or implement custom logic)
	po_name = po_list[0]
	
	try:
		# Get transport details from PO
		po_data = frappe.db.get_value(
			"Purchase Order",
			po_name,
			["custom_transport_cost", "custom_lcv_exchange_rate"],
			as_dict=True
		)
		
		if not po_data:
			return
		
		# Auto-fill transport cost
		if flt(po_data.get("custom_transport_cost")) > 0:
			doc.custom_transport_cost = po_data.custom_transport_cost
		
		# Auto-fill LCV exchange rate
		if flt(po_data.get("custom_lcv_exchange_rate")) > 0:
			doc.custom_lcv_exchange_rate = po_data.custom_lcv_exchange_rate
		
		# Notify user if values were filled
		if doc.custom_transport_cost or doc.custom_lcv_exchange_rate:
			frappe.msgprint(
				_("Transport details auto-filled from Purchase Order: {0}").format(po_name),
				indicator="blue",
				alert=True
			)
	
	except Exception as e:
		# Don't block - just log
		frappe.log_error(
			message=f"Auto-fill from PO {po_name} failed: {str(e)}",
			title="Transport Auto-Fill Error"
		)


# ============================================================
# UTILITY FUNCTIONS FOR EXTERNAL CALLS
# ============================================================

def get_lcv_summary(pi_name):
	"""
	Get summary of all LCVs linked to a Purchase Invoice.
	
	Args:
		pi_name: Purchase Invoice name
	
	Returns:
		dict: Summary information
	"""
	
	lcvs = frappe.get_all(
		"Landed Cost Voucher",
		filters={"custom_purchase_invoice": pi_name},
		fields=["name", "custom_lcv_type", "docstatus", "posting_date"],
		order_by="creation desc"
	)
	
	total_amount = 0.0
	
	for lcv in lcvs:
		# Get total amount from taxes
		taxes_total = frappe.db.sql("""
			SELECT SUM(amount) as total
			FROM `tabLanded Cost Taxes and Charges`
			WHERE parent = %s
		""", lcv.name, as_dict=True)
		
		if taxes_total and taxes_total[0].total:
			lcv['total_amount'] = flt(taxes_total[0].total, 2)
			total_amount += lcv['total_amount']
		else:
			lcv['total_amount'] = 0.0
		
		# Status label
		if lcv.docstatus == 0:
			lcv['status_label'] = "Draft"
		elif lcv.docstatus == 1:
			lcv['status_label'] = "Submitted"
		else:
			lcv['status_label'] = "Cancelled"
	
	return {
		"purchase_invoice": pi_name,
		"lcv_count": len(lcvs),
		"total_lcv_amount": flt(total_amount, 2),
		"lcvs": lcvs
	}


def reprocess_lcv(pi_name, lcv_type=None):
	"""
	Reprocess LCV creation for a Purchase Invoice.
	Useful for manual intervention or corrections.
	
	Args:
		pi_name: Purchase Invoice name
		lcv_type: "Transport" or "Price Variance" or None for both
	
	Returns:
		dict: Result summary
	"""
	
	# Get PI document
	doc = frappe.get_doc("Purchase Invoice", pi_name)
	
	if doc.docstatus != 1:
		frappe.throw(_("Purchase Invoice must be submitted to create LCV"))
	
	results = {
		"transport_lcv": None,
		"variance_lcv": None,
		"errors": []
	}
	
	# Process Transport LCV
	if not lcv_type or lcv_type == "Transport":
		try:
			_handle_transport_lcv_creation(doc)
			results["transport_lcv"] = "Success"
		except Exception as e:
			results["errors"].append(f"Transport LCV: {str(e)}")
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Manual Transport LCV Creation Failed: {pi_name}"
			)
	
	# Process Variance LCV
	if not lcv_type or lcv_type == "Price Variance":
		try:
			_handle_variance_lcv_creation(doc)
			results["variance_lcv"] = "Success"
		except Exception as e:
			results["errors"].append(f"Variance LCV: {str(e)}")
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Manual Variance LCV Creation Failed: {pi_name}"
			)
	
	return results
