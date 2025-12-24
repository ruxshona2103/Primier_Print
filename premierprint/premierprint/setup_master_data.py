import frappe

def setup_all():
	"""PREMIER PRINT - TO'LIQ TIZIM SETUP"""
	frappe.db.begin()
	try:
		print("=" * 60)
		print("🚀 PREMIER PRINT TIZIM O'RNATILMOQDA...")
		print("=" * 60)

		# 0. Warehouse Types (Muhim: Eng birinchi!)
		create_warehouse_types()

		# 1. Kompaniyalar
		create_companies()

		# 2. Omborlar
		create_custom_warehouses()

		# 3. To'lov Turlari
		create_mode_of_payments()

		# 4. Kassa va Hisoblar
		create_and_link_accounts()

		# 5. Stock Entry Tiplari
		create_stock_entry_types()

		# 6. Harajat Tizimi (YANGI!)
		setup_expense_system()

		frappe.db.commit()
		print("\n" + "=" * 60)
		print("✅ G'ALABA! TIZIM MUVAFFAQIYATLI O'RNATILDI!")
		print("=" * 60)
		print("\n⚠️  MUHIM: Bench ni restart qiling:")
		print("    bench restart")
		print("\n📋 Yaratilgan:")
		print("   - 4 ta Kompaniya (Premier Print + 3 ta sub)")
		print("   - 19 ta Ombor (ierarxiya bilan)")
		print("   - 4 ta Mode of Payment")
		print("   - 11 ta Bank/Cash Account")
		print("   - 3 ta Stock Entry Type")
		print("   - 18 ta Expense Category")
		print("   - 1 ta Client Script (Payment Entry)")
		print("=" * 60)
	except Exception as e:
		frappe.db.rollback()
		print("\n" + "=" * 60)
		print(f"❌ KRITIK XATOLIK: {str(e)}")
		print("=" * 60)
		print(frappe.get_traceback())


# ============================================================
# 0. WAREHOUSE TYPES
# ============================================================
def create_warehouse_types():
	print("\n📦 [1/7] Warehouse Types yaratilmoqda...")
	types = ["Transit", "Material", "Work In Progress", "Finished Goods"]
	created = 0
	for t in types:
		if not frappe.db.exists("Warehouse Type", t):
			doc = frappe.new_doc("Warehouse Type")
			doc.name = t
			doc.insert(ignore_permissions=True)
			created += 1
			print(f"   ✓ {t}")
	print(f"   Jami: {created} ta yangi, {len(types) - created} ta mavjud")


# ============================================================
# 1. KOMPANIYALAR
# ============================================================
def create_companies():
	print("\n🏢 [2/7] Kompaniyalar yaratilmoqda...")
	companies = [
		{"name": "Premier Print", "abbr": "PP", "is_group": 1, "parent": None},
		{"name": "Полиграфия", "abbr": "П", "is_group": 0, "parent": "Premier Print"},
		{"name": "Реклама", "abbr": "Р", "is_group": 0, "parent": "Premier Print"},
		{"name": "Сувенир", "abbr": "С", "is_group": 0, "parent": "Premier Print"},
	]

	created = 0
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
				doc.flags.ignore_warehouse_creation = True
				doc.insert(ignore_permissions=True)
				created += 1
				print(f"   ✓ {comp['name']}")
			except Exception as e:
				print(f"   ✗ {comp['name']}: {str(e)}")
		else:
			print(f"   = {comp['name']} (mavjud)")
	print(f"   Jami: {created} ta yangi, {len(companies) - created} ta mavjud")


# ============================================================
# 2. OMBORLAR
# ============================================================
def create_custom_warehouses():
	print("\n🏭 [3/7] Omborlar yaratilmoqda...")

	structure = [
		# Guruhlar (is_group=1)
		("All Warehouses - PP", None, "Premier Print"),
		("All Warehouses - П", "All Warehouses - PP", "Полиграфия"),
		("All Warehouses - Р", "All Warehouses - PP", "Реклама"),
		("All Warehouses - С", "All Warehouses - PP", "Сувенир"),

		("Poligrafiya Sexi - П", "All Warehouses - П", "Полиграфия"),
		("Reklama Sexi - Р", "All Warehouses - Р", "Реклама"),
		("Suvenir Sexi - С", "All Warehouses - С", "Сувенир"),

		# Real Omborlar (is_group=0)
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

	created = 0
	skipped = 0
	for wh_name, parent, company in structure:
		if not frappe.db.exists("Warehouse", wh_name):
			# Parent tekshirish
			if parent and not frappe.db.exists("Warehouse", parent):
				print(f"   ⚠ {wh_name} (Parent yo'q: {parent})")
				skipped += 1
				continue

			doc = frappe.new_doc("Warehouse")
			doc.name = wh_name
			doc.warehouse_name = wh_name.rsplit(' - ', 1)[0]
			doc.company = company
			doc.parent_warehouse = parent

			# Is Group aniqlash: Agar bu nom structure da biror parent bo'lsa
			is_group = 1 if any(x[1] == wh_name for x in structure) else 0
			doc.is_group = is_group

			try:
				doc.insert(ignore_permissions=True)
				created += 1
				print(f"   ✓ {wh_name}")
			except frappe.NameError:
				pass
		else:
			print(f"   = {wh_name} (mavjud)")

	print(f"   Jami: {created} ta yangi, {skipped} ta o'tkazib yuborildi")


# ============================================================
# 3. MODE OF PAYMENTS
# ============================================================
def create_mode_of_payments():
	print("\n💳 [4/7] To'lov Turlari yaratilmoqda...")
	modes = ["Наличные", "Пластик", "Терминал", "Перечисления"]
	created = 0
	for mode in modes:
		if not frappe.db.exists("Mode of Payment", mode):
			doc = frappe.new_doc("Mode of Payment")
			doc.mode_of_payment = mode
			doc.type = "Cash" if mode == "Наличные" else "Bank"
			doc.insert(ignore_permissions=True)
			created += 1
			print(f"   ✓ {mode}")
		else:
			print(f"   = {mode} (mavjud)")
	print(f"   Jami: {created} ta yangi, {len(modes) - created} ta mavjud")


# ============================================================
# 4. KASSA VA HISOBLAR + MODE OF PAYMENT LINKING
# ============================================================
def create_and_link_accounts():
	print("\n💰 [5/7] Kassa va Hisoblar yaratilmoqda...")

	# FIXED: Premier Print uchun ham default hisob!
	accounts_map = [
		# Premier Print (GROUP uchun markaziy kassa)
		("Premier Print", "Центральная касса PP UZS", "Cash", "Наличные"),

		# Реклама
		("Реклама", "Азизбек Сейф UZS", "Cash", "Наличные"),
		("Реклама", "Счёт в банке Азизбек UZS", "Bank", "Перечисления"),
		("Реклама", "Пластик Азизбек 1592 UZS", "Bank", "Пластик"),
		("Реклама", "Азизбек терминал UZS", "Bank", "Терминал"),
		("Реклама", "Касса Азизбек UZS", "Cash", None),

		# Полиграфия
		("Полиграфия", "Головной UZS", "Cash", "Наличные"),
		("Полиграфия", "PREMIER PRINT РАСЧЁТНЫЙ СЧЁТ UZS", "Bank", "Перечисления"),
		("Полиграфия", "Касса ресепшн головной UZS", "Cash", None),
		("Полиграфия", "Касса Ёкуб UZS", "Cash", None),

		# Сувенир
		("Сувенир", "Пластик ЧП МАЛИКОВ", "Bank", "Пластик"),
		("Сувенир", "Пластик 5315 Камол", "Bank", None),
	]

	created_accounts = 0
	linked_modes = 0

	for company, acc_name, acc_type, mode in accounts_map:
		if not frappe.db.exists("Company", company):
			continue

		abbr = frappe.db.get_value("Company", company, "abbr")
		account_id = f"{acc_name} - {abbr}"

		# 1. Hisobni Yaratish
		if not frappe.db.exists("Account", account_id):
			# Parent qidirish
			parent_acc = frappe.db.get_value("Account", {
				"company": company,
				"account_type": acc_type,
				"is_group": 1
			}, "name")

			if not parent_acc:
				parent_acc = frappe.db.get_value("Account", {
					"company": company,
					"is_group": 1,
					"root_type": "Asset"
				}, "name")

			if parent_acc:
				ac = frappe.new_doc("Account")
				ac.account_name = acc_name
				ac.company = company
				ac.parent_account = parent_acc
				ac.account_type = acc_type
				ac.currency = "UZS"
				ac.insert(ignore_permissions=True)
				created_accounts += 1
				print(f"   ✓ {account_id}")
			else:
				print(f"   ✗ Parent topilmadi: {company} - {acc_type}")

		# 2. Mode of Payment ga Ulash
		if mode and frappe.db.exists("Mode of Payment", mode) and frappe.db.exists("Account",
																				   account_id):
			mop = frappe.get_doc("Mode of Payment", mode)

			# Bu kompaniya uchun qator bormi?
			found = False
			for row in mop.accounts:
				if row.company == company:
					row.default_account = account_id
					found = True
					break

			if not found:
				mop.append("accounts", {
					"company": company,
					"default_account": account_id
				})

			mop.save(ignore_permissions=True)
			linked_modes += 1
			print(f"   🔗 {mode} → {account_id}")

	print(f"   Jami: {created_accounts} ta hisob, {linked_modes} ta link")


# ============================================================
# 5. STOCK ENTRY TYPES
# ============================================================
def create_stock_entry_types():
	print("\n📦 [6/7] Stock Entry Tiplari yaratilmoqda...")
	types = [
		("Услуги по заказу", "Material Issue"),
		("Расход по заказу", "Material Issue"),
		("Перемещение", "Material Transfer")
	]
	created = 0
	for name, purpose in types:
		if not frappe.db.exists("Stock Entry Type", name):
			d = frappe.new_doc("Stock Entry Type")
			d.name = name
			d.purpose = purpose
			d.insert(ignore_permissions=True)
			created += 1
			print(f"   ✓ {name}")
		else:
			print(f"   = {name} (mavjud)")
	print(f"   Jami: {created} ta yangi, {len(types) - created} ta mavjud")


# ============================================================
# 6. HARAJAT TIZIMI (EXPENSE SYSTEM)
# ============================================================
def setup_expense_system():
	print("\n💸 [7/7] Harajat Tizimi o'rnatilmoqda...")

	# 6.1. Expense Category DocType
	create_expense_category_doctype()

	# 6.2. Harajat hisoblarini yaratish
	create_expense_accounts()

	# 6.3. Expense Category larni yaratish
	create_expense_categories()

	# 6.4. Client Script
	create_client_script()

	print("   ✅ Harajat tizimi tayyor!")


def create_expense_category_doctype():
	"""Expense Category DocType"""
	if frappe.db.exists("DocType", "Expense Category"):
		print("   = Expense Category DocType (mavjud)")
		return

	doc = frappe.get_doc({
		"doctype": "DocType",
		"name": "Expense Category",
		"module": "Accounts",
		"custom": 1,
		"autoname": "field:expense_name",
		"naming_rule": "By fieldname",
		"fields": [
			{
				"fieldname": "expense_name",
				"label": "Название расхода",
				"fieldtype": "Data",
				"reqd": 1,
				"unique": 1,
				"in_list_view": 1
			},
			{
				"fieldname": "expense_account",
				"label": "Счет расхода",
				"fieldtype": "Link",
				"options": "Account",
				"reqd": 1,
				"in_list_view": 1
			},
			{
				"fieldname": "company",
				"label": "Company",
				"fieldtype": "Link",
				"options": "Company",
				"default": "Premier Print"
			},
			{
				"fieldname": "description",
				"label": "Описание",
				"fieldtype": "Small Text"
			}
		],
		"permissions": [
			{
				"role": "Accounts Manager",
				"read": 1,
				"write": 1,
				"create": 1,
				"delete": 1
			},
			{
				"role": "Accounts User",
				"read": 1,
				"write": 1,
				"create": 1
			}
		]
	})
	doc.insert(ignore_permissions=True)
	print("   ✓ Expense Category DocType yaratildi")


def create_expense_accounts():
	"""Harajat hisoblarini yaratish"""
	company = "Premier Print"
	abbr = frappe.db.get_value("Company", company, "abbr")

	# Parent hisob: Indirect Expenses
	parent = frappe.db.get_value("Account", {
		"company": company,
		"account_name": "Indirect Expenses",
		"is_group": 1
	}, "name")

	if not parent:
		print("   ✗ Indirect Expenses parent topilmadi")
		return

	accounts = [
		"Расходы - Аренда",
		"Расходы - Офис",
		"Расходы - Канцтовары",
		"Расходы - Хозтовары",
		"Расходы - Транспорт",
		"Расходы - Банк",
		"Прочие приходы",
		"Прочие расходы",
		"Расходы - Связь",
		"Расходы - Интернет",
		"Налоги",
		"Расходы - Командировки",
		"Расходы - Документы"
	]

	created = 0
	for acc_name in accounts:
		account_id = f"{acc_name} - {abbr}"

		if not frappe.db.exists("Account", account_id):
			acc = frappe.new_doc("Account")
			acc.account_name = acc_name
			acc.company = company
			acc.parent_account = parent
			acc.account_type = "Expense Account"
			acc.insert(ignore_permissions=True)
			created += 1

	print(f"   ✓ {created} ta harajat hisobi yaratildi")


def create_expense_categories():
	"""Expense Categories"""
	company = "Premier Print"
	abbr = frappe.db.get_value("Company", company, "abbr")

	expenses = [
		("Аренда", "Расходы - Аренда"),
		("Продукты для офиса", "Расходы - Офис"),
		("Канцтовары", "Расходы - Канцтовары"),
		("Хозтовары", "Расходы - Хозтовары"),
		("Такси, доставка, яндекс", "Расходы - Транспорт"),
		("Комиссия банка", "Расходы - Банк"),
		("Комиссия карта", "Расходы - Банк"),
		("Прочие приходы", "Прочие приходы"),
		("Прочие расходы", "Прочие расходы"),
		("Сотовая связь", "Расходы - Связь"),
		("Интернет", "Расходы - Интернет"),
		("Земельный налог", "Налоги"),
		("Подоходный налог", "Налоги"),
		("Налог на прибыль", "Налоги"),
		("Налог по НДС", "Налоги"),
		("Налог на имущество", "Налоги"),
		("Командировочные расходы", "Расходы - Командировки"),
		("Документы", "Расходы - Документы")
	]

	created = 0
	for exp_name, account_name in expenses:
		account_id = f"{account_name} - {abbr}"

		if not frappe.db.exists("Account", account_id):
			continue

		if not frappe.db.exists("Expense Category", exp_name):
			exp_doc = frappe.new_doc("Expense Category")
			exp_doc.expense_name = exp_name
			exp_doc.expense_account = account_id
			exp_doc.company = company
			exp_doc.insert(ignore_permissions=True)
			created += 1

	print(f"   ✓ {created} ta Expense Category yaratildi")


def create_client_script():
	"""Payment Entry uchun Client Script"""
	script_name = "Payment Entry - Expenses Support"

	# Eski scriptni o'chirish
	if frappe.db.exists("Client Script", script_name):
		frappe.delete_doc("Client Script", script_name, ignore_permissions=True)

	script_content = """frappe.ui.form.on('Payment Entry', {
    onload: function(frm) {
        // Party Type ga Expenses option qo'shamiz
        let options = frm.fields_dict['party_type'].df.options;
        if (typeof options === 'string') {
            options = options.split('\\n');
        }
        if (!options.includes('Expenses')) {
            options.push('Expenses');
        }
        frm.fields_dict['party_type'].df.options = options;
        frm.refresh_field('party_type');
    },

    party_type: function(frm) {
        if (frm.doc.party_type === 'Expenses') {
            // Party field ni Expense Category ga o'zgartiramiz
            frm.set_df_property('party', 'label', 'Категория расхода');
            frm.set_df_property('party', 'options', 'Expense Category');
            frm.set_df_property('party', 'reqd', 1);
            frm.set_df_property('party_name', 'hidden', 1);

            // Tozalash
            frm.set_value('party', '');
            frm.set_value('party_name', '');
        } else {
            // Oddiy holatga qaytarish
            frm.set_df_property('party', 'label', 'Party');
            frm.set_df_property('party_name', 'hidden', 0);

            // Options ni tiklash
            if (frm.doc.party_type === 'Customer') {
                frm.set_df_property('party', 'options', 'Customer');
            } else if (frm.doc.party_type === 'Supplier') {
                frm.set_df_property('party', 'options', 'Supplier');
            } else if (frm.doc.party_type === 'Employee') {
                frm.set_df_property('party', 'options', 'Employee');
            }
        }
    },

    party: function(frm) {
        if (frm.doc.party_type === 'Expenses' && frm.doc.party) {
            // Party Name ni o'rnatish
            frm.set_value('party_name', frm.doc.party);

            // Expense Account ni olish va Paid To ga qo'yish
            frappe.db.get_value('Expense Category', frm.doc.party, 'expense_account', (r) => {
                if (r && r.expense_account) {
                    frm.set_value('paid_to', r.expense_account);
                }
            });
        }
    }
});"""

	client_script = frappe.get_doc({
		"doctype": "Client Script",
		"name": script_name,
		"dt": "Payment Entry",
		"enabled": 1,
		"script": script_content
	})
	client_script.insert(ignore_permissions=True)
	print(f"   ✓ Client Script: {script_name}")


# ============================================================
# 7. STOCK ENTRY TO'LIQ SETUP (YANGI!)
# ============================================================
def setup_stock_entry_complete():
	"""
	STOCK ENTRY - TO'LIQ PROFESSIONAL SETUP

	Bu funksiya barcha Stock Entry muammolarini hal qiladi:
	1. Barcha eski Client Script larni o'chiradi
	2. "From Sub Company" ni Property Setter orqali yashiradi
	3. Yangi, to'g'ri Client Script yaratadi
	4. Cache ni tozalaydi

	Ishlatish:
	    bench --site primier.com execute premierprint.premierprint.setup_master_data.setup_stock_entry_complete
	"""
	frappe.db.begin()
	try:
		print("\n" + "="*70)
		print("🚀 STOCK ENTRY - TO'LIQ PROFESSIONAL SETUP")
		print("="*70 + "\n")

		# Step 1: Eski Client Script larni o'chirish
		disable_old_stock_entry_scripts()

		# Step 2: Property Setter orqali "From Sub Company" ni yashirish
		hide_from_sub_company_field()

		# Step 3: Yangi Client Script yaratish
		create_stock_entry_client_script()

		# Step 4: Cache tozalash
		clear_all_caches()

		frappe.db.commit()

		print("\n" + "="*70)
		print("✅ MUVAFFAQIYAT! STOCK ENTRY SETUP TUGADI!")
		print("="*70)
		print("\n📋 KEYINGI QADAMLAR:")
		print("1. bench restart")
		print("2. Browser: Ctrl + Shift + R (Hard Reload)")
		print("3. Stock Entry formani tekshiring\n")
		print("✅ KUTILGAN NATIJA:")
		print("   - 'From Sub Company' YASHIRIN")
		print("   - Shartli UI (3 ta tur uchun) ISHLAYDI")
		print("   - Warehouse filtrlash TO'G'RI ISHLAYDI\n")
		print("="*70)

	except Exception as e:
		frappe.db.rollback()
		print("\n" + "="*70)
		print(f"❌ XATOLIK: {str(e)}")
		print("="*70)
		print(frappe.get_traceback())


def disable_old_stock_entry_scripts():
	"""Barcha eski Stock Entry Client Script larni o'chirish"""
	print("📝 [1/4] Eski Client Script larni o'chirish...")

	scripts = frappe.get_all('Client Script',
		filters={'dt': 'Stock Entry'},
		fields=['name', 'enabled']
	)

	if scripts:
		print(f"   Topildi: {len(scripts)} ta script")
		disabled_count = 0
		for script in scripts:
			try:
				doc = frappe.get_doc('Client Script', script.name)
				if doc.enabled:
					doc.enabled = 0
					doc.save(ignore_permissions=True)
					disabled_count += 1
					print(f"   ✅ O'chirildi: {script.name}")
				else:
					print(f"   = Allaqachon o'chirilgan: {script.name}")
			except Exception as e:
				print(f"   ⚠️  Xatolik ({script.name}): {str(e)}")

		print(f"   ✅ Jami o'chirildi: {disabled_count} ta\n")
	else:
		print("   ℹ️  Hech qanday eski script topilmadi\n")


def hide_from_sub_company_field():
	"""Property Setter orqali 'From Sub Company' ni yashirish"""
	print("🔒 [2/4] 'From Sub Company' maydonini yashirish...")

	try:
		# Mavjud Property Setter ni tekshirish
		existing = frappe.db.exists('Property Setter', {
			'doc_type': 'Stock Entry',
			'field_name': 'custom_from_sub_company',
			'property': 'hidden'
		})

		if existing:
			# Mavjud bo'lsa, yangilash
			prop = frappe.get_doc('Property Setter', existing)
			prop.value = '1'
			prop.save(ignore_permissions=True)
			print("   ✅ Mavjud Property Setter yangilandi")
		else:
			# Yangi yaratish
			prop = frappe.get_doc({
				'doctype': 'Property Setter',
				'doctype_or_field': 'DocField',
				'doc_type': 'Stock Entry',
				'field_name': 'custom_from_sub_company',
				'property': 'hidden',
				'value': '1',
				'property_type': 'Check'
			})
			prop.insert(ignore_permissions=True)
			print("   ✅ Yangi Property Setter yaratildi")

		print("   ✅ 'From Sub Company' maydoni yashirildi\n")

	except Exception as e:
		print(f"   ⚠️  Warning: {str(e)}")
		print("   ℹ️  Davom etamiz...\n")


def create_stock_entry_client_script():
	"""Yangi Stock Entry Client Script yaratish"""
	print("📝 [3/4] Yangi Client Script yaratish...")

	script_name = "Stock Entry - Professional v3.0"

	# Script kodi
	script_code = """frappe.ui.form.on('Stock Entry', {
    setup: function(frm) {
        frm.set_query('stock_entry_type', function() {
            return { filters: [['Stock Entry Type', 'name', 'in', ['Перемещение', 'Расход по заказу', 'Услуги по заказу']]] };
        });
        frm.set_query('custom_sales_order_item', function() {
            if (!frm.doc.custom_sales_order) return { filters: { 'parent': 'null' } };
            return { query: 'premierprint.utils.stock_entry.get_sales_order_items_query', filters: { 'sales_order': frm.doc.custom_sales_order } };
        });
        frm.set_query('s_warehouse', 'items', function(doc) {
            if (doc.stock_entry_type === 'Перемещение' && doc.company) {
                return { filters: { 'company': doc.company, 'is_group': 0 } };
            }
        });
        frm.set_query('t_warehouse', 'items', function(doc) {
            if (doc.stock_entry_type === 'Перемещение' && doc.custom_to_sub_company) {
                return { filters: { 'company': doc.custom_to_sub_company, 'is_group': 0 } };
            }
        });
    },
    refresh: function(frm) {
        frm.set_df_property('custom_from_sub_company', 'hidden', 1);
        frm.set_df_property('custom_from_sub_company', 'reqd', 0);
        apply_ui_rules(frm);
    },
    stock_entry_type: function(frm) { apply_ui_rules(frm); },
    company: function(frm) { frm.refresh_field('items'); },
    custom_to_sub_company: function(frm) { frm.refresh_field('items'); },
    custom_sales_order: function(frm) {
        frm.set_value('custom_sales_order_item', '');
        frm.clear_table('items');
        frm.refresh_field('items');
    },
    custom_sales_order_item: function(frm) {
        if (!frm.doc.custom_sales_order_item) return;
        frm.clear_table('items');
        frappe.call({
            method: 'premierprint.utils.stock_entry.get_bom_materials',
            args: { sales_order_item_id: frm.doc.custom_sales_order_item },
            freeze: true,
            callback: function(r) {
                if (r.message && r.message.length > 0) {
                    r.message.forEach(function(m) {
                        let row = frm.add_child('items');
                        frappe.model.set_value(row.doctype, row.name, m);
                    });
                    frm.refresh_field('items');
                    frappe.show_alert({ message: 'BOM yuklandi!', indicator: 'green' }, 3);
                }
                apply_ui_rules(frm);
            }
        });
    }
});

frappe.ui.form.on('Stock Entry Detail', {
    s_warehouse: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.s_warehouse) auto_set_cost_center(frm, cdt, cdn, row.s_warehouse);
    },
    t_warehouse: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.t_warehouse && !row.s_warehouse) auto_set_cost_center(frm, cdt, cdn, row.t_warehouse);
    },
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (frm.doc.stock_entry_type === 'Перемещение' && row.item_code && frm.doc.company) {
            fetch_item_price(frm, cdt, cdn, row.item_code, frm.doc.company);
        }
    }
});

function apply_ui_rules(frm) {
    const type = frm.doc.stock_entry_type;
    frm.set_df_property('custom_from_sub_company', 'hidden', 1);
    frm.set_df_property('custom_from_sub_company', 'reqd', 0);
    if (type === 'Перемещение') {
        frm.set_df_property('custom_sales_order', 'hidden', 1);
        frm.set_df_property('custom_sales_order_item', 'hidden', 1);
        frm.set_df_property('custom_supplier', 'hidden', 1);
        frm.set_df_property('custom_supplier', 'reqd', 0);
        frm.set_df_property('company', 'hidden', 0);
        frm.set_df_property('custom_to_sub_company', 'hidden', 0);
        frm.set_df_property('custom_to_sub_company', 'reqd', 1);
        frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 1);
        frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 1);
    } else if (type === 'Расход по заказу') {
        frm.set_df_property('custom_sales_order', 'hidden', 0);
        frm.set_df_property('custom_sales_order_item', 'hidden', 0);
        frm.set_df_property('custom_supplier', 'hidden', 1);
        frm.set_df_property('custom_supplier', 'reqd', 0);
        frm.set_df_property('custom_to_sub_company', 'hidden', 1);
        frm.set_df_property('custom_to_sub_company', 'reqd', 0);
        frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 1);
        frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 1);
    } else if (type === 'Услуги по заказу') {
        frm.set_df_property('custom_sales_order', 'hidden', 0);
        frm.set_df_property('custom_sales_order_item', 'hidden', 0);
        frm.set_df_property('custom_supplier', 'hidden', 0);
        frm.set_df_property('custom_supplier', 'reqd', 1);
        frm.set_df_property('custom_to_sub_company', 'hidden', 1);
        frm.set_df_property('custom_to_sub_company', 'reqd', 0);
        frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 0);
        frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'read_only', 0);
        frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 0);
    }
    frm.refresh_fields();
}

function auto_set_cost_center(frm, cdt, cdn, warehouse) {
    if (!warehouse) return;
    let w = warehouse.toLowerCase();
    let cc = w.includes('poli') ? '100 - Poligrafiya Department' : w.includes('reklama') ? '200 - Reklama Department' : w.includes('suvenir') ? '300 - Suvenir Department' : '100 - Poligrafiya Department';
    frappe.model.set_value(cdt, cdn, 'cost_center', cc);
}

function fetch_item_price(frm, cdt, cdn, item_code, company) {
    if (!item_code || !company) return;
    frappe.db.get_value('Company', company, 'default_price_list', (r) => {
        let filters = { 'item_code': item_code };
        if (r && r.default_price_list) filters['price_list'] = r.default_price_list;
        frappe.call({
            method: 'frappe.client.get_list',
            args: { doctype: 'Item Price', filters: filters, fields: ['price_list_rate'], order_by: 'modified desc', limit: 1 },
            callback: function(r) {
                frappe.model.set_value(cdt, cdn, 'basic_rate', r.message && r.message.length > 0 ? r.message[0].price_list_rate || 0 : 0);
            }
        });
    });
}"""

	try:
		# Mavjud script ni tekshirish
		if frappe.db.exists('Client Script', script_name):
			script = frappe.get_doc('Client Script', script_name)
			script.script = script_code
			script.enabled = 1
			script.save(ignore_permissions=True)
			print(f"   ✅ Mavjud script yangilandi: {script_name}")
		else:
			script = frappe.get_doc({
				'doctype': 'Client Script',
				'name': script_name,
				'dt': 'Stock Entry',
				'view': 'Form',
				'enabled': 1,
				'script': script_code
			})
			script.insert(ignore_permissions=True)
			print(f"   ✅ Yangi script yaratildi: {script_name}")

		print("   ✅ Client Script FAOL holatda\n")

	except Exception as e:
		print(f"   ❌ Xatolik: {str(e)}\n")
		raise


def clear_all_caches():
	"""Barcha cache larni tozalash"""
	print("🧹 [4/4] Cache tozalash...")

	try:
		frappe.clear_cache()
		print("   ✅ Frappe cache tozalandi")

		from frappe.website.render import clear_cache as clear_website_cache
		clear_website_cache()
		print("   ✅ Website cache tozalandi\n")

	except Exception as e:
		print(f"   ⚠️  Warning: {str(e)}")
		print("   ℹ️  Davom etamiz...\n")


