import frappe


def setup_all():
	"""PREMIER PRINT - ONLY STRUCTURE & FINANCE DATA"""
	frappe.db.begin()
	try:
		print("=" * 60)
		print("🚀 PREMIER PRINT: BAZA TIKLANMOQDA...")
		print("=" * 60)

		# 1. TOZALASH (Eski expense dumlarni yo'qotish)
		nuke_junk()

		# 2. STRUKTURA
		create_warehouse_types()
		create_companies()
		create_custom_warehouses()

		# 3. MOLIYA
		create_mode_of_payments()
		create_financial_accounts()

		# 4. STOCK
		create_stock_entry_types()

		frappe.db.commit()
		print("\n" + "=" * 60)
		print("✅ G'ALABA! Tizim toza va struktura joyida.")
		print("=" * 60)
	except Exception as e:
		frappe.db.rollback()
		print(f"❌ XATOLIK: {str(e)}")


# =========================================================
# 0. TOZALASH (Jarrohlik)
# =========================================================
def nuke_junk():
	print("\n🧹 [1/6] Eski 'Expense' qoldiqlari tozalanmoqda...")

	# 1. Expense Category DocType ni o'chirish
	if frappe.db.exists("DocType", "Expense Category"):
		frappe.delete_doc("DocType", "Expense Category", force=True)
		print("   ✓ Expense Category DocType o'chirildi")

	# 2. Payment Entry dagi eski script va fieldlarni o'chirish
	frappe.db.sql("DELETE FROM `tabClient Script` WHERE dt = 'Payment Entry'")

	fields = ["custom_is_expense", "custom_payment_target", "custom_expense_category",
			  "expense_category"]
	for f in fields:
		if frappe.db.exists("Custom Field", f"Payment Entry-{f}"):
			frappe.delete_doc("Custom Field", f"Payment Entry-{f}", force=True)

	# 3. Party Type optionsni tozalash (Standartga qaytarish)
	if frappe.db.exists("Property Setter", "Payment Entry-party_type-options"):
		frappe.delete_doc("Property Setter", "Payment Entry-party_type-options", force=True)


# =========================================================
# 1. STRUKTURA
# =========================================================
def create_warehouse_types():
	print("\n📦 [2/6] Warehouse Types...")
	for t in ["Transit", "Material", "Work In Progress", "Finished Goods"]:
		if not frappe.db.exists("Warehouse Type", t):
			frappe.get_doc({"doctype": "Warehouse Type", "name": t}).insert(
				ignore_permissions=True)


def create_companies():
	print("\n🏢 [3/6] Kompaniyalar...")
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
			if comp["parent"]: doc.parent_company = comp["parent"]
			doc.create_chart_of_accounts_based_on = "Standard Template"
			doc.flags.ignore_warehouse_creation = True
			doc.insert(ignore_permissions=True)
			print(f"   ✓ {comp['name']}")


def create_custom_warehouses():
	print("\n🏭 [4/6] Omborlar...")
	# Sening aniq ro'yxating
	whs = [
		("Markaziy Sklad - PP", "Premier Print"),
		("Brak va Chiqindi - PP", "Premier Print"),

		("Сергили склад - П", "Полиграфия"),
		("Сергили производство - П", "Полиграфия"),
		("Офис склад - П", "Полиграфия"),

		("Shirokoformat - Р", "Реклама"),
		("Rezka - Р", "Реклама"),
		("Mimaki - Р", "Реклама"),
		("Ekosolvent - Р", "Реклама"),
		("Reka - Р", "Реклама"),
		("Склад производство - Р", "Реклама"),

		("Основной склад - С", "Сувенир"),
		("Витрина офис - С", "Сувенир"),
	]
	for name, comp in whs:
		if not frappe.db.exists("Warehouse", name):
			d = frappe.new_doc("Warehouse")
			d.warehouse_name = name.split(" - ")[0]
			d.name = name
			d.company = comp
			try:
				d.insert(ignore_permissions=True); print(f"   ✓ {name}")
			except:
				pass


# =========================================================
# 2. MOLIYA
# =========================================================
def create_mode_of_payments():
	print("\n💳 [5/6] To'lov Turlari...")
	for m in ["Наличные", "Пластик", "Терминал", "Перечисления"]:
		if not frappe.db.exists("Mode of Payment", m):
			frappe.get_doc({"doctype": "Mode of Payment", "mode_of_payment": m,
							"type": "Cash" if m == "Наличные" else "Bank"}).insert(
				ignore_permissions=True)


def create_financial_accounts():
	print("\n💰 [6/6] Kassa va Banklar...")
	accounts = [
		("Реклама", "Азизбек Сейф UZS", "Cash", "Наличные"),
		("Реклама", "Касса Азизбек UZS", "Cash", "Наличные"),
		("Реклама", "Счёт в банке Азизбек UZS", "Bank", "Перечисления"),
		("Реклама", "Пластик Азизбек 1592 UZS", "Bank", "Пластик"),
		("Реклама", "Азизбек терминал UZS", "Bank", "Терминал"),
		("Полиграфия", "Головной UZS", "Cash", "Наличные"),
		("Полиграфия", "Касса ресепшн головной UZS", "Cash", "Наличные"),
		("Полиграфия", "Касса Ёкуб UZS", "Cash", "Наличные"),
		("Полиграфия", "PREMIER PRINT РАСЧЁТНЫЙ СЧЁТ UZS", "Bank", "Перечисления"),
		("Сувенир", "Пластик ЧП МАЛИКОВ", "Bank", "Пластик"),
		("Сувенир", "Пластик 5315 Камол", "Bank", "Пластик"),
	]
	for company, acc_name, acc_type, mode in accounts:
		if not frappe.db.exists("Company", company): continue
		abbr = frappe.db.get_value("Company", company, "abbr")
		acc_id = f"{acc_name} - {abbr}"

		# Hisob yaratish
		if not frappe.db.exists("Account", acc_id):
			parent = frappe.db.get_value("Account", {"company": company, "account_type": acc_type,
													 "is_group": 1}, "name")
			if not parent: parent = frappe.db.get_value("Account",
														{"company": company, "is_group": 1,
														 "root_type": "Asset"}, "name")
			if parent:
				frappe.get_doc({
					"doctype": "Account", "account_name": acc_name, "company": company,
					"parent_account": parent, "account_type": acc_type, "currency": "UZS"
				}).insert(ignore_permissions=True)
				print(f"   ✓ Hisob: {acc_id}")

		# Mode ga ulash
		if mode and frappe.db.exists("Account", acc_id):
			mop = frappe.get_doc("Mode of Payment", mode)
			exists = False
			for row in mop.accounts:
				if row.company == company: exists = True; break
			if not exists:
				mop.append("accounts", {"company": company, "default_account": acc_id})
				mop.save(ignore_permissions=True)


def create_stock_entry_types():
	for t in [("Услуги по заказу", "Material Issue"), ("Расход по заказу", "Material Issue"),
			  ("Перемещение", "Material Transfer")]:
		if not frappe.db.exists("Stock Entry Type", t[0]):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": t[0], "purpose": t[1]}).insert(
				ignore_permissions=True)
