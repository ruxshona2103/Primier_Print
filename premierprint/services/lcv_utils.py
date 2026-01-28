import frappe
from frappe import _
from frappe.utils import flt, nowdate

def convert_to_company_currency(amount, from_currency, to_currency, conversion_rate):
	"""
	Smart Currency Conversion with Ambiguous Rate Detection.

	This function intelligently handles both direct and indirect exchange rates by:
	1. Fetching the system's official exchange rate from ERPNext
	2. Comparing the input rate against the official rate
	3. Determining if the input is a multiplier (direct) or divisor (indirect)
	4. Applying the correct mathematical operation

	SCENARIO A (Transport LCV - Indirect Rate):
		- Input: 50,000 UZS with rate 12,099.18 (User model: 1 USD = 12,099 UZS)
		- System Rate: 0.00008265 (Official: 1 UZS = 0.00008 USD)
		- Detection: Input rate is ~146,000x larger than system rate
		- Operation: DIVIDE (50,000 / 12,099.18 = ~4.13 USD) ✅

	SCENARIO B (Variance LCV - Direct Rate):
		- Input: 50,000 UZS with rate 0.00008265 (System model: 1 UZS = 0.00008 USD)
		- System Rate: 0.00008265 (Official: 1 UZS = 0.00008 USD)
		- Detection: Input rate matches system rate
		- Operation: MULTIPLY (50,000 * 0.00008265 = ~4.13 USD) ✅

	Args:
		amount: Amount to convert
		from_currency: Source currency code
		to_currency: Target currency code
		conversion_rate: Exchange rate (may be direct or indirect)

	Returns:
		float: Converted amount in target currency
	"""
	amount = flt(amount)
	conversion_rate = flt(conversion_rate)

	# Edge case: Invalid rate
	if conversion_rate <= 0:
		frappe.log_error(
			message=f"Invalid conversion rate ({conversion_rate}) provided for {from_currency} -> {to_currency}. Using rate 1.0.",
			title="Currency Conversion Warning"
		)
		conversion_rate = 1.0

	# Same currency - no conversion needed
	if from_currency == to_currency:
		return amount

	# ============================================================
	# INTELLIGENT RATE DETECTION ALGORITHM
	# ============================================================
	try:
		# Step 1: Fetch official system exchange rate from ERPNext
		# This uses the same API that the UI uses (erpnext.setup.utils.get_exchange_rate)
		from erpnext.setup.utils import get_exchange_rate

		official_rate = None
		try:
			official_rate = get_exchange_rate(
				from_currency=from_currency,
				to_currency=to_currency,
				transaction_date=nowdate()
			)
		except Exception:
			# Try reverse lookup if direct lookup fails
			try:
				reverse_rate = get_exchange_rate(
					from_currency=to_currency,
					to_currency=from_currency,
					transaction_date=nowdate()
				)
				if reverse_rate and reverse_rate > 0:
					official_rate = 1.0 / reverse_rate
			except Exception:
				pass

		if not official_rate or official_rate <= 0:
			# Last resort: Use input rate as-is with multiplication
			frappe.log_error(
				message=f"No official exchange rate found for {from_currency} -> {to_currency}. Using input rate {conversion_rate} directly.",
				title="Currency Rate Fallback"
			)
			return amount * conversion_rate

		# Step 2: Calculate deviation ratio between input rate and official rate
		# This tells us if the user passed an inverse rate
		deviation_ratio = conversion_rate / official_rate if official_rate != 0 else 1.0

		# Step 3: Also check inverse deviation (official / input)
		# This helps detect when the input is the reciprocal
		inverse_deviation_ratio = official_rate / conversion_rate if conversion_rate != 0 else 1.0

		# Step 4: Determine the operation based on deviation
		# LOGIC:
		# - If deviation_ratio ≈ 1 (within 10% tolerance): Input is DIRECT → MULTIPLY
		# - If deviation_ratio >> 1 (>100x): Input is INDIRECT (inverse) → DIVIDE
		# - If inverse_deviation_ratio ≈ 1 (within 10%): Input is already inverse → DIVIDE

		TOLERANCE = 0.10  # 10% tolerance for "same rate"
		INVERSE_THRESHOLD = 100  # If >100x different, it's inverse

		if abs(deviation_ratio - 1.0) < TOLERANCE:
			# Case 1: Input rate matches official rate (within tolerance) → Direct multiplication
			# Example: Input 0.00008265 matches Official 0.00008265
			operation = "multiply"
			result = amount * conversion_rate

		elif deviation_ratio > INVERSE_THRESHOLD:
			# Case 2: Input rate is way larger than official → User passed inverse rate
			# Example: Input 12,099 vs Official 0.00008265 → ratio ~146,000,000x
			# This means user input is (1 / official_rate), so we need to divide
			operation = "divide"
			result = amount / conversion_rate

		elif inverse_deviation_ratio > INVERSE_THRESHOLD:
			# Case 3: Official rate is way larger than input → Input is already inverted
			# Rare case, but handle it
			operation = "divide"
			result = amount / conversion_rate

		else:
			# Case 4: Moderate deviation - analyze currency strength
			# For weak->strong conversion (like UZS->USD), official rate should be small (<1)
			# If input rate is large (>1), it's likely inverse
			if official_rate < 1.0 and conversion_rate > 1.0:
				# Official expects small multiplier, input gave large divisor
				operation = "divide"
				result = amount / conversion_rate
			elif official_rate > 1.0 and conversion_rate < 1.0:
				# Official expects large multiplier, input gave small multiplier (inverted)
				operation = "divide"
				result = amount / conversion_rate
			else:
				# Default to multiplication if uncertain
				operation = "multiply"
				result = amount * conversion_rate

		# Log the decision for audit trail
		frappe.logger().debug(
			f"Currency Conversion: {amount} {from_currency} -> {to_currency} | "
			f"Input Rate: {conversion_rate} | Official Rate: {official_rate} | "
			f"Deviation: {deviation_ratio:.2f}x | Operation: {operation.upper()} | "
			f"Result: {result:.2f}"
		)

		return flt(result, 2)

	except ImportError:
		# Fallback: ERPNext not available (unlikely in production)
		frappe.log_error(
			message="ERPNext setup.utils not available. Using simple multiplication.",
			title="Currency Conversion Fallback"
		)
		return amount * conversion_rate

	except Exception as e:
		# Unexpected error - log and use safe fallback
		frappe.log_error(
			message=f"Currency conversion error: {str(e)}\n"
			        f"Amount: {amount}, From: {from_currency}, To: {to_currency}, Rate: {conversion_rate}",
			title="Currency Conversion Error"
		)
		# Safe fallback: assume input rate is correct for multiplication
		return amount * conversion_rate

def get_stock_received_but_not_billed_account(company):
	"""
	Stock Received But Not Billed hisobini topish.
	Bu funksiya sizda YETISHMAYOTGAN edi.
	"""
	# 1. Kompaniya sozlamalaridan olish
	account = frappe.db.get_value("Company", company, "stock_received_but_not_billed")

	# 2. Agar u yerda bo'lmasa, taxminiy qidirish (Fallback)
	if not account:
		account = frappe.db.get_value("Account", {
			"account_name": "Stock Received But Not Billed",
			"company": company,
			"is_group": 0
		}, "name")

	if not account:
		frappe.throw(
			_("Kompaniya sozlamalarida 'Stock Received But Not Billed' hisobi topilmadi. Iltimos, Company sozlamalarini tekshiring.")
		)

	return account

def get_transport_expense_account(company):
	"""
	Transport xarajat hisobini topish.
	"""
	# Aniq nom bo'yicha
	account = frappe.db.get_value(
		"Account",
		filters={
			"account_name": "Transport Xarajati (LCV)",
			"company": company,
			"is_group": 0,
			"disabled": 0
		},
		fieldname="name"
	)

	if account:
		return account

	# Kalit so'z bo'yicha
	account = frappe.db.get_value(
		"Account",
		filters={
			"account_name": ["like", "%Transport%"],
			"account_type": ["in", ["Expense Included In Valuation", "Direct Expense"]],
			"company": company,
			"is_group": 0,
			"disabled": 0
		},
		fieldname="name",
		order_by="creation desc"
	)

	if account:
		return account

	frappe.throw(
		_("Transport xarajat hisobi topilmadi. 'Transport Xarajati (LCV)' nomli hisob yarating.")
	)
