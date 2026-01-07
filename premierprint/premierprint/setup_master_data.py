import logging
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

logger = logging.getLogger(__name__)


def setup_all() -> None:
	"""Barcha master-ma'lumotlarni sozlash: Kompaniyalar, Hisoblar, Omborlar va Fieldlar"""
	frappe.db.begin()
	try:
		logger.info("PremierPrint: setup_all boshlandi")

		# 1. Tozalash va Fundamental struktura
		nuke_expense_category()
		create_warehouse_types()

		# 2. Kompaniyalar ierarxiyasi
		create_companies()

		# 3. Moliya: Kassalar va Banklar (Chart of Accounts)
		create_all_accounts()

		# 4. Omborxona va Stock sozlamalari
		create_custom_warehouses()
		create_stock_custom_fields()
		create_stock_entry_types()

		frappe.db.commit()
		logger.info("PremierPrint: setup_all muvaffaqiyatli yakunlandi")
	except Exception:
		frappe.db.rollback()
		logger.exception("PremierPrint: setup_all jarayonida xatolik yuz berdi")
		raise


def nuke_expense_category() -> None:
	if frappe.db.exists("DocType", "Expense Category"):
		frappe.delete_doc("DocType", "Expense Category", force=True)
		logger.info("Deleted DocType: Expense Category")


def create_warehouse_types() -> None:
	for t in ("Transit", "Material", "Work In Progress", "Finished Goods"):
		if not frappe.db.exists("Warehouse Type", t):
			frappe.get_doc({"doctype": "Warehouse Type", "name": t}).insert(
				ignore_permissions=True)


def create_companies() -> None:
	"""Kompaniyalarni ierarxiya va ruxsatnomalar bilan yaratish"""
	companies = [
		{"name": "Premier Print", "abbr": "PP", "is_group": 1, "parent": None},
		{"name": "Полиграфия", "abbr": "П", "is_group": 0, "parent": "Premier Print"},
		{"name": "Реклама", "abbr": "Р", "is_group": 0, "parent": "Premier Print"},
		{"name": "Сувенир", "abbr": "С", "is_group": 0, "parent": "Premier Print"},
	]
	for comp in companies:
		if not frappe.db.exists("Company", comp["name"]):
			doc = frappe.new_doc("Company")
			doc.company_name = comp["name"]
			doc.abbr = comp["abbr"]
			doc.default_currency = "UZS"
			doc.country = "Uzbekistan"
			doc.is_group = comp["is_group"]
			if comp["parent"]:
				doc.parent_company = comp["parent"]
				# Sub-kompaniyalarda erkin hisob ochish ruxsati
				doc.allow_account_creation_against_child_company = 1
			doc.create_chart_of_accounts_based_on = "Standard Template"
			doc.flags.ignore_warehouse_creation = True
			doc.insert(ignore_permissions=True)
			logger.info(f"Created Company: {comp['name']}")


def create_all_accounts() -> None:
	"""Kassalar va Bank ledgerlarini ierarxiya bo'yicha yaratish"""
	accounts_data = [
		# REKLAMA (- P)
		{"name": "Азизбек Сейф UZS", "type": "Cash", "parent": "Cash In Hand",
		 "company": "Реклама", "abbr": "Р"},
		{"name": "Касса Азизбек UZS", "type": "Cash", "parent": "Cash In Hand",
		 "company": "Реклама", "abbr": "Р"},
		{"name": "Счёт в банке Азизбек UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Реклама", "abbr": "Р"},
		{"name": "Пластик Азизбек 1592 UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Реклама", "abbr": "Р"},
		{"name": "Азизбек терминал UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Реклама", "abbr": "Р"},

		# POLIGRAFIYA (- П)
		{"name": "Головной UZS", "type": "Cash", "parent": "Cash In Hand", "company": "Полиграфия",
		 "abbr": "П"},
		{"name": "Касса ресепшн головной UZS", "type": "Cash", "parent": "Cash In Hand",
		 "company": "Полиграфия", "abbr": "П"},
		{"name": "Касса Ёкуб UZS", "type": "Cash", "parent": "Cash In Hand",
		 "company": "Полиграфия", "abbr": "П"},
		{"name": "PREMIER PRINT РАСЧЁТНЫЙ СЧЁТ UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Полиграфия", "abbr": "П"},

		# SUVENIR (- С)
		{"name": "Пластик ЧП МАЛИКОВ UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Сувенир", "abbr": "С"},
		{"name": "Пластик 5315 Каmol UZS", "type": "Bank", "parent": "Bank Accounts",
		 "company": "Сувенир", "abbr": "С"},
	]

	for acc in accounts_data:
		full_name = f"{acc['name']} - {acc['abbr']}"
		parent_id = f"{acc['parent']} - {acc['abbr']}"

		if not frappe.db.exists("Account", full_name):
			doc = frappe.new_doc("Account")
			doc.account_name = acc['name']
			doc.parent_account = parent_id
			doc.company = acc['company']
			doc.account_type = acc['type']
			doc.account_currency = "UZS"
			doc.insert(ignore_permissions=True)
			logger.info(f"Created Account: {full_name}")


def create_custom_warehouses() -> None:
	warehouses = [
		("Markaziy Sklad - PP", "Premier Print"),
		("Brak va Chiqindi - PP", "Premier Print"),
		("Сергили склад - П", "Полиграфия"),
		("Офис склад - П", "Полиграфия"),
		("Shirokoformat - Р", "Реклама"),
		("Rezka - Р", "Реклама"),
		("Основной склад - С", "Сувенир"),
	]
	for name, comp in warehouses:
		if not frappe.db.exists("Warehouse", name):
			d = frappe.new_doc("Warehouse")
			d.warehouse_name = name.split(" - ")[0]
			d.name = name
			d.company = comp
			d.insert(ignore_permissions=True)


def create_stock_custom_fields() -> None:
	# Custom fields mantiig'i (avvalgi kodingizdagi kabi)
	custom_fields = {
		"Stock Entry": [
			{"fieldname": "custom_sales_order", "label": "Заказ покупателя", "fieldtype": "Link",
			 "options": "Sales Order", "insert_after": "stock_entry_type"},
			{"fieldname": "custom_supplier", "label": "Поставщик услуг", "fieldtype": "Link",
			 "options": "Supplier", "insert_after": "stock_entry_type"},
		]
	}
	create_custom_fields(custom_fields, ignore_permissions=True)


def create_stock_entry_types() -> None:
	stock_entry_types = [
		{"name": "Расход по заказу", "purpose": "Material Issue"},
		{"name": "Перемещение", "purpose": "Material Transfer"},
	]
	for et in stock_entry_types:
		if not frappe.db.exists("Stock Entry Type", et["name"]):
			doc = frappe.new_doc("Stock Entry Type")
			doc.name = et["name"]
			doc.purpose = et["purpose"]
			doc.insert(ignore_permissions=True)
