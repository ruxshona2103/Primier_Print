import frappe
from frappe import _
from frappe.utils import flt


def create_lcv_from_pi(doc, method):
	# 1. Validatsiya
	if not doc.custom_transport_cost or doc.custom_transport_cost <= 0:
		return

	pr_list = list(set([d.purchase_receipt for d in doc.items if d.purchase_receipt]))
	if not pr_list:
		frappe.msgprint(_("⚠️ PR topilmadi, LCV yaratilmadi."), indicator='orange')
		return

	try:
		# 2. VALYUTA VA KURS MANTIGI (SMART LOGIC)
		company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')
		lcv_currency = doc.custom_lcv_currency

		raw_amount = flt(doc.custom_transport_cost)
		exchange_rate = flt(doc.custom_lcv_exchange_rate)
		final_amount = 0.0

		# Agar kurs 0 bo'lsa, xato
		if exchange_rate <= 0:
			frappe.throw(_("Valyuta kursi 0 bo'lishi mumkin emas"))

		# --- MANTIQ ---
		if lcv_currency == company_currency:
			# Valyuta bir xil (USD -> USD)
			final_amount = raw_amount

		elif company_currency == "USD" and lcv_currency != "USD":
			# Kompaniya USD, Xarajat UZS
			if exchange_rate > 1:
				# Ssenariy A: Kurs 12800 (Odam kiritdi)
				# 1,280,000 UZS / 12,800 = 100 USD
				final_amount = raw_amount / exchange_rate
			else:
				# Ssenariy B: Kurs 0.000078 (Tizim kiritdi)
				# 1,280,000 UZS * 0.000078 = 100 USD
				final_amount = raw_amount * exchange_rate

		else:
			# Universal (Standart ko'paytirish)
			final_amount = raw_amount * exchange_rate
		# ----------------------

		# 3. LCV Yaratish
		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = doc.company
		lcv.posting_date = doc.posting_date

		for pr_name in pr_list:
			pr_grand_total = frappe.db.get_value("Purchase Receipt", pr_name, "grand_total")
			lcv.append("purchase_receipts", {
				"receipt_document_type": "Purchase Receipt",
				"receipt_document": pr_name,
				"grand_total": pr_grand_total
			})

		lcv.get_items_from_purchase_receipts()

		expense_account = get_transport_account(doc.company)

		lcv.append("taxes", {
			"expense_account": expense_account,
			"description": f"Transport: {raw_amount} {lcv_currency} (Rate: {exchange_rate})",
			"amount": final_amount
		})

		if doc.custom_lcv_allocation == "Amount":
			lcv.distribute_charges_based_on = "Amount"
		else:
			lcv.distribute_charges_based_on = "Qty"

		lcv.save()
		lcv.submit()

		frappe.msgprint(
			_("✅ LCV Yaratildi. <br>Kiritingiz: {0} {1} <br>Hisoblandi: {2} {3}").format(
				raw_amount, lcv_currency, final_amount, company_currency
			),
			indicator='green'
		)

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"LCV Error {doc.name}")
		frappe.msgprint(f"Xatolik: {str(e)}", indicator='red')


def get_transport_account(company):
	# Bu qism o'zgarmaydi
	account = frappe.db.get_value("Account", filters={"account_name": "Transport Xarajati (LCV)",
													  "company": company, "is_group": 0},
								  fieldname="name")
	if not account:
		account = frappe.db.get_value("Account",
									  filters={"account_name": ["like", "%Transport Xarajati%"],
											   "account_type": ["in",
																["Expense Included In Valuation",
																 "Direct Expense"]],
											   "company": company, "is_group": 0},
									  fieldname="name")
	if not account:
		frappe.throw(f"Transport shoti topilmadi: {company}")
	return account
