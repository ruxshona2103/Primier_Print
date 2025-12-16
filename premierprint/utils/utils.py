import frappe
import requests
from frappe.utils import today, flt


def update_cbu_exchange_rate():
	try:
		url = "https://cbu.uz/oz/arkhiv-kursov-valyut/json/"
		response = requests.get(url, timeout=10)
		response.raise_for_status()
		data = response.json()

		usd_rate = None
		for currency in data:
			if currency.get('Ccy') == 'USD':
				usd_rate = flt(currency.get('Rate'))
				break

		if not usd_rate:
			return

		current_date = today()

		# 1-QADAM: USD -> UZS (Dollardan So'mga)
		if not frappe.db.exists("Currency Exchange", {
			"date": current_date,
			"from_currency": "USD",
			"to_currency": "UZS"
		}):
			frappe.get_doc({
				"doctype": "Currency Exchange",
				"date": current_date,
				"from_currency": "USD",
				"to_currency": "UZS",
				"exchange_rate": usd_rate
			}).insert(ignore_permissions=True)
			print(f"To'g'ri kurs yaratildi: 1 USD = {usd_rate} UZS")

		# 2-QADAM: UZS -> USD (So'mdan Dollarga - TESKARI)
		if not frappe.db.exists("Currency Exchange", {
			"date": current_date,
			"from_currency": "UZS",
			"to_currency": "USD"
		}):
			# Teskari kursni hisoblash (1 / kurs)
			inverse_rate = 1 / usd_rate

			frappe.get_doc({
				"doctype": "Currency Exchange",
				"date": current_date,
				"from_currency": "UZS",
				"to_currency": "USD",
				"exchange_rate": inverse_rate
			}).insert(ignore_permissions=True)
			print(f"Teskari kurs yaratildi: 1 UZS = {inverse_rate:.10f} USD")

		frappe.db.commit()

	except Exception as e:
		frappe.log_error(f"Valyuta xatosi: {str(e)}", "Auto Currency Update")
		print(f"Xatolik: {str(e)}")
