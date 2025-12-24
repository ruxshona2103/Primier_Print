import frappe


def setup_all():
	frappe.db.begin()
	try:
		# 0. Eng avval Warehouse Type larni to'g'rilash (Critical Dependency)
		create_warehouse_types()

		# 1. Kompaniyalarni yaratish
		create_companies()

		# 2. Omborlarni yaratish
		create_custom_warehouses()

		# 3. To'lov Turlarini yaratish
		create_mode_of_payments()

		# 4. Kassa va Hisoblar (Smart Link)
		create_and_link_accounts()

		# 5. Stock Entry Tiplari
		create_stock_entry_types()

		frappe.db.commit()
		print("✅ G'ALABA! Tizim muvaffaqiyatli va xatosiz tiklandi.")
	except Exception as e:
		frappe.db.rollback()
		print(f"❌ KRITIK XATOLIK: {str(e)}")
		print(frappe.get_traceback())


def create_warehouse_types():
	print("--- Warehouse Types...")
	types = ["Transit", "Material", "Work In Progress", "Finished Goods"]
	for t in types:
		if not frappe.db.exists("Warehouse Type", t):
			doc = frappe.new_doc("Warehouse Type")
			doc.name = t
			doc.insert(ignore_permissions=True)
			print(f"+++ Type yaratildi: {t}")


def create_companies():
	print("--- Kompaniyalar...")
	companies = [
		{"name": "Premier Print", "abbr": "PP", "is_group": 1, "parent": None},
		{"name": "Полиграфия", "abbr": "П", "is_group": 0, "parent": "Premier Print"},
		{"name": "Реклама", "abbr": "Р", "is_group": 0, "parent": "Premier Print"},
		{"name": "Сувенир", "abbr": "С", "is_group": 0, "parent": "Premier Print"},
	]

	for comp in companies:
		if not frappe.db.exists("Company", comp["name"]):
			try:
				doc = frappe.new_doc("Company")
				doc.company_name = comp["name"]
				doc.abbr = comp["abbr"]
				doc.default_currency = "UZS"
				doc.country = "Uzbekistan"
				doc.is_group = comp["is_group"]
				if comp["parent"]:
					doc.parent_company = comp["parent"]
				doc.create_chart_of_accounts_based_on = "Standard Template"

				# Bu yerda muhim: Transit ombor yaratishda xato chiqmasligi uchun
				doc.flags.ignore_warehouse_creation = True

				doc.insert(ignore_permissions=True)
				print(f"+++ Kompaniya: {comp['name']}")
			except Exception as e:
				print(f"!!! Xato ({comp['name']}): {str(e)}")
		else:
			print(f"=== Kompaniya mavjud: {comp['name']}")


def create_custom_warehouses():
	print("--- Omborlar...")

	# Format: (Nomi, Parent Warehouse, Company)
	# DIQQAT: Parent nomlari aniq bo'lishi kerak
	structure = [
		# Guruhlar
		("All Warehouses - PP", None, "Premier Print"),
		("All Warehouses - П", "All Warehouses - PP", "Полиграфия"),
		("All Warehouses - Р", "All Warehouses - PP", "Реклама"),
		("All Warehouses - С", "All Warehouses - PP", "Сувенир"),

		("Poligrafiya Sexi - П", "All Warehouses - П", "Полиграфия"),
		("Reklama Sexi - Р", "All Warehouses - Р", "Реклама"),
		("Suvenir Sexi - С", "All Warehouses - С", "Сувенир"),

		# Real Omborlar
		("Markaziy Xomashyo Skladi - PP", "All Warehouses - PP", "Premier Print"),
		("Brak va Chiqindi - PP", "All Warehouses - PP", "Premier Print"),

		("Poli Material - П", "Poligrafiya Sexi - П", "Полиграфия"),
		("Poli WIP - П", "Poligrafiya Sexi - П", "Полиграфия"),
		("Poli Tayyor - П", "Poligrafiya Sexi - П", "Полиграфия"),

		("Reklama Material - Р", "Reklama Sexi - Р", "Реклама"),
		("Reklama WIP - Р", "Reklama Sexi - Р", "Реклама"),
		("Reklama Tayyor - Р", "Reklama Sexi - Р", "Реклама"),

		("Suvenir Material - С", "Suvenir Sexi - С", "Сувенир"),
		("Suvenir WIP - С", "Suvenir Sexi - С", "Сувенир"),
		("Suvenir Tayyor - С", "Suvenir Sexi - С", "Сувенир"),
		("Suvenir Vitrina - С", "Suvenir Sexi - С", "Сувенир"),
	]

	for wh_name, parent, company in structure:
		if not frappe.db.exists("Warehouse", wh_name):
			# Parentni tekshirish
			if parent and not frappe.db.exists("Warehouse", parent):
				# Agar parent hali yo'q bo'lsa, uni o'tkazib yuboramiz (keyingi aylanishda yaratilishi mumkin emas, tartib muhim)
				# Lekin biz tartibni to'g'ri qo'ydik: Avval Group, keyin Leaf
				print(f"⚠️ Parent '{parent}' topilmadi. '{wh_name}' tashlab ketildi.")
				continue

			doc = frappe.new_doc("Warehouse")
			doc.name = wh_name  # ID ni majburlab beramiz
			doc.warehouse_name = wh_name.rsplit(' - ', 1)[0]
			doc.company = company
			doc.parent_warehouse = parent

			# Is Group mantiqi: Agar bu nom structure dagi biror parent bo'lsa -> Group
			is_group = 1 if any(x[1] == wh_name for x in structure) else 0
			doc.is_group = is_group

			try:
				doc.insert(ignore_permissions=True)
				print(f"+++ Ombor: {wh_name}")
			except frappe.NameError:
				pass


def create_mode_of_payments():
	print("--- To'lov Turlari...")
	modes = ["Наличные", "Пластик", "Терминал", "Перечисления"]
	for mode in modes:
		if not frappe.db.exists("Mode of Payment", mode):
			doc = frappe.new_doc("Mode of Payment")
			doc.mode_of_payment = mode
			doc.type = "Cash" if mode == "Наличные" else "Bank"
			doc.insert(ignore_permissions=True)
			print(f"+++ Mode: {mode}")


def create_and_link_accounts():
	print("--- Kassa va Hisoblar...")

	# Format: (Kompaniya, Hisob Nomi, Turi, Mode of Payment)
	accounts_map = [
		# Реклама (E'tibor ber: Bitta Mode ga faqat bitta default account ulanadi)
		("Реклама", "Азизбек Сейф UZS", "Cash", "Наличные"),
		("Реклама", "Счёт в банке Азизбек UZS", "Bank", "Перечисления"),
		("Реклама", "Пластик Азизбек 1592 UZS", "Bank", "Пластик"),
		("Реклама", "Азизбек терминал UZS", "Bank", "Терминал"),

		# Qo'shimcha hisoblar (Mode ga ulanmaydi, lekin yaratiladi)
		("Реклама", "Касса Азизбек UZS", "Cash", None),

		# Полиграфия
		("Полиграфия", "Головной UZS", "Cash", "Наличные"),
		("Полиграфия", "PREMIER PRINT РАСЧЁТНЫЙ СЧЁТ UZS", "Bank", "Перечисления"),

		# Qo'shimcha
		("Полиграфия", "Касса ресепшн головной UZS", "Cash", None),
		("Полиграфия", "Касса Ёкуб UZS", "Cash", None),

		# Сувенир
		("Сувенир", "Пластик ЧП МАЛИКОВ", "Bank", "Пластик"),

		# Qo'shimcha
		("Сувенир", "Пластик 5315 Камол", "Bank", None),
	]

	for company, acc_name, acc_type, mode in accounts_map:
		if not frappe.db.exists("Company", company): continue

		abbr = frappe.db.get_value("Company", company, "abbr")
		account_id = f"{acc_name} - {abbr}"

		# 1. Hisobni Yaratish
		if not frappe.db.exists("Account", account_id):
			parent_acc = frappe.db.get_value("Account",
											 {"company": company, "account_type": acc_type,
											  "is_group": 1}, "name")

			if not parent_acc:
				parent_acc = frappe.db.get_value("Account",
												 {"company": company, "is_group": 1,
												  "root_type": "Asset"}, "name")

			if parent_acc:
				ac = frappe.new_doc("Account")
				ac.account_name = acc_name
				ac.company = company
				ac.parent_account = parent_acc
				ac.account_type = acc_type
				ac.currency = "UZS"
				ac.insert(ignore_permissions=True)
				print(f"+++ Hisob: {account_id}")

		# 2. Mode of Payment ga Ulash (Faqat mode bo'lsa)
		if mode and frappe.db.exists("Account", account_id):
			mop = frappe.get_doc("Mode of Payment", mode)

			# --- PROFESSIONAL LOGIKA ---
			# Agar bu kompaniya uchun allaqachon qator bo'lsa -> Yangilaymiz
			# Agar yo'q bo'lsa -> Qo'shamiz
			found = False
			for row in mop.accounts:
				if row.company == company:
					# DIQQAT: Agar allaqachon boshqa hisob ulangan bo'lsa,
					# biz uni o'zgartiramiz (chunki 1 ta kompaniyaga 1 ta default bo'ladi)
					row.default_account = account_id
					found = True
					break

			if not found:
				row = mop.append("accounts", {})
				row.company = company
				row.default_account = account_id

			mop.save(ignore_permissions=True)
			print(f"🔗 Link (Updated): {mode} -> {account_id}")


def create_stock_entry_types():
	print("--- Stock Entry Tiplari...")
	types = [
		("Услуги по заказу", "Material Issue"),
		("Расход по заказу", "Material Issue"),
		("Перемещение", "Material Transfer")
	]
	for name, purpose in types:
		if not frappe.db.exists("Stock Entry Type", name):
			d = frappe.new_doc("Stock Entry Type")
			d.name = name
			d.purpose = purpose
			d.insert(ignore_permissions=True)
			print(f"+++ Type: {name}")
