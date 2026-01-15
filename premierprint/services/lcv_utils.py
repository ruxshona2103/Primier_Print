import frappe
from frappe import _
from frappe.utils import flt

def convert_to_company_currency(amount, from_currency, to_currency, conversion_rate):
	"""
	Valyuta konvertatsiyasi.
	"""
	amount = flt(amount)
	conversion_rate = flt(conversion_rate)

	if conversion_rate <= 0:
		conversion_rate = 1.0

	# Agar valyutalar bir xil bo'lsa
	if from_currency == to_currency:
		return amount

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
