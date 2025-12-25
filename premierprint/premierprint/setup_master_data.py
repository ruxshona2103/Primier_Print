import frappe


def setup_all():
	"""PREMIER PRINT - TIZIMNI TIKLASH (ONLY DATA)"""
	frappe.db.begin()
	try:
		print("=" * 60)
		print("🚀 PREMIER PRINT: MASTER DATA SETUP...")
		print("=" * 60)

		# 1. Struktura
		create_warehouse_types()
		create_companies()
		create_custom_warehouses()

		# 2. Moliya
		create_mode_of_payments()
		create_financial_accounts()

		# 3. Xarajatlar (Faqat ma'lumot to'ldiradi, DocType yaratmaydi!)
		setup_expense_data()

		# 4. Stock
		create_stock_entry_types()

		# 5. Client Script (UI uchun)
		create_payment_entry_client_script()

		frappe.db.commit()
		print("\n" + "=" * 60)
		print("✅ G'ALABA! Barcha ma'lumotlar yuklandi.")
		print("=" * 60)
	except Exception as e:
		frappe.db.rollback()
		print(f"❌ XATOLIK: {str(e)}")
	# print(frappe.get_traceback())


# ---------------------------------------------------------
# 1. STRUKTURA
# ---------------------------------------------------------
def create_warehouse_types():
	print("\n📦 Warehouse Types...")
	for t in ["Transit", "Material", "Work In Progress", "Finished Goods"]:
		if not frappe.db.exists("Warehouse Type", t):
			frappe.get_doc({"doctype": "Warehouse Type", "name": t}).insert(
				ignore_permissions=True)


def create_companies():
	print("\n🏢 Kompaniyalar...")
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
	print("\n🏭 Omborlar...")
	structure = [
		("All Warehouses - PP", None, "Premier Print", 1),
		("All Warehouses - П", "All Warehouses - PP", "Полиграфия", 1),
		("All Warehouses - Р", "All Warehouses - PP", "Реклама", 1),
		("All Warehouses - С", "All Warehouses - PP", "Сувенир", 1),
		("Poligrafiya Sexi - П", "All Warehouses - П", "Полиграфия", 1),
		("Reklama Sexi - Р", "All Warehouses - Р", "Реклама", 1),
		("Suvenir Sexi - С", "All Warehouses - С", "Сувенир", 1),

		("Markaziy Xomashyo Skladi - PP", "All Warehouses - PP", "Premier Print", 0),
		("Brak va Chiqindi - PP", "All Warehouses - PP", "Premier Print", 0),
		("Сергили склад - П", "Poligrafiya Sexi - П", "Полиграфия", 0),
		("Сергили производство - П", "Poligrafiya Sexi - П", "Полиграфия", 0),
		("Офис склад - П", "Poligrafiya Sexi - П", "Полиграфия", 0),
		("Shirokoformat - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Rezka - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Mimaki - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Ekosolvent - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Reka - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Склад производство - Р", "Reklama Sexi - Р", "Реклама", 0),
		("Основной склад - С", "Suvenir Sexi - С", "Сувенир", 0),
		("Витрина офис - С", "Suvenir Sexi - С", "Сувенир", 0),
	]
	for name, parent, company, is_group in structure:
		if not frappe.db.exists("Warehouse", name):
			if parent and not frappe.db.exists("Warehouse", parent): continue
			d = frappe.new_doc("Warehouse")
			d.name = name
			d.warehouse_name = name.rsplit(' - ', 1)[0]
			d.company = company
			d.parent_warehouse = parent
			d.is_group = is_group
			try:
				d.insert(ignore_permissions=True); print(f"   ✓ {name}")
			except:
				pass


def create_mode_of_payments():
	print("\n💳 To'lov Turlari...")
	for m in ["Наличные", "Пластик", "Терминал", "Перечисления"]:
		if not frappe.db.exists("Mode of Payment", m):
			d = frappe.new_doc("Mode of Payment")
			d.mode_of_payment = m
			d.type = "Cash" if m == "Наличные" else "Bank"
			d.insert(ignore_permissions=True)


def create_financial_accounts():
	print("\n💰 Kassa va Banklar...")
	accounts_map = [
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
	for company, acc_name, acc_type, mode in accounts_map:
		if not frappe.db.exists("Company", company): continue
		abbr = frappe.db.get_value("Company", company, "abbr")
		account_id = f"{acc_name} - {abbr}"
		if not frappe.db.exists("Account", account_id):
			parent = frappe.db.get_value("Account", {"company": company, "account_type": acc_type,
													 "is_group": 1}, "name")
			if not parent: parent = frappe.db.get_value("Account",
														{"company": company, "is_group": 1,
														 "root_type": "Asset"}, "name")
			if parent:
				ac = frappe.new_doc("Account")
				ac.account_name = acc_name
				ac.company = company
				ac.parent_account = parent
				ac.account_type = acc_type
				ac.currency = "UZS"
				ac.insert(ignore_permissions=True)
				print(f"   ✓ Hisob: {account_id}")
		if mode and frappe.db.exists("Account", account_id):
			mop = frappe.get_doc("Mode of Payment", mode)
			exists = False
			for row in mop.accounts:
				if row.company == company: exists = True; break
			if not exists:
				mop.append("accounts", {"company": company, "default_account": account_id})
				mop.save(ignore_permissions=True)


# # ---------------------------------------------------------
# # 3. XARAJAT MA'LUMOTLARI (DocType yaratmaydi!)
# # ---------------------------------------------------------
# def setup_expense_data():
# 	print("\n💸 Harajat Ma'lumotlari...")
#
# 	# MUHIM: Agar DocType yo'q bo'lsa, to'xtaymiz
# 	if not frappe.db.exists("DocType", "Expense Category"):
# 		print("⚠️ DIQQAT: 'Expense Category' DocType topilmadi. Uni qo'lda yarating!")
# 		return
#
# 	expenses = [
# 		"Аренда", "Продукта офис", "Расходы - Канцтовары", "Расходы - Хозтовары",
# 		"Такси, доставка, яндекс", "Комиссия банка", "Комиссия карта",
# 		"Прочие приходы", "Прочие расходы", "Расходы - Сотовая связь",
# 		"Расходы - Интернет", "Земельный налог", "Подоходный налог",
# 		"Налог на прибыль", "Налог по НДС", "Налог на имущество",
# 		"Командировочные расходы", "Расходы – Документы"
# 	]
#
# 	for company in ["Полиграфия", "Реклама", "Сувенир"]:
# 		if not frappe.db.exists("Company", company): continue
# 		abbr = frappe.db.get_value("Company", company, "abbr")
#
# 		# Hisob raqamlari uchun Parent (Expense)
# 		parent = frappe.db.get_value("Account",
# 									 {"company": company, "is_group": 1, "root_type": "Expense"},
# 									 "name")
#
# 		if parent:
# 			for exp in expenses:
# 				acc_id = f"{exp} - {abbr}"
# 				# 1. Hisobni yaratish (Account)
# 				if not frappe.db.exists("Account", acc_id):
# 					ac = frappe.new_doc("Account")
# 					ac.account_name = exp
# 					ac.company = company
# 					ac.parent_account = parent
# 					ac.account_type = "Tax" if "Налог" in exp else "Expense Account"
# 					ac.insert(ignore_permissions=True)
# 					print(f"   ✓ Account: {acc_id}")
#
# 				# 2. Kategoriyani yaratish (Expense Category)
# 				if not frappe.db.exists("Expense Category", exp):
# 					# Faqat Hisob (Account) mavjud bo'lsa yaratamiz
# 					if frappe.db.exists("Account", acc_id):
# 						ec = frappe.new_doc("Expense Category")
# 						ec.expense_name = exp
# 						ec.expense_account = acc_id
# 						ec.company = company
# 						ec.insert(ignore_permissions=True)
# 						print(f"   ✓ Category: {exp}")


def create_stock_entry_types():
	for t in [("Услуги по заказу", "Material Issue"), ("Расход по заказу", "Material Issue"),
			  ("Перемещение", "Material Transfer")]:
		if not frappe.db.exists("Stock Entry Type", t[0]):
			frappe.get_doc({"doctype": "Stock Entry Type", "name": t[0], "purpose": t[1]}).insert(
				ignore_permissions=True)


# ---------------------------------------------------------
# 4. CLIENT SCRIPT (Payment Entry uchun)
# ---------------------------------------------------------
def create_payment_entry_client_script():
	print("\n📜 Payment Entry Script...")
	script_name = "Payment Entry - Smart Filters"

	if frappe.db.exists("Client Script", script_name):
		frappe.delete_doc("Client Script", script_name)

	js_code = """
frappe.ui.form.on('Payment Entry', {
    setup: function(frm) {
        let options = frm.fields_dict['party_type'].df.options;
        if (typeof options === 'string' && !options.includes('Expense Category')) {
            frm.set_df_property('party_type', 'options', options + '\\nExpense Category');
        }
    },

    refresh: function(frm) {
        frm.trigger('set_account_filter');
        frm.trigger('toggle_expense_mode');
    },

    mode_of_payment: function(frm) { frm.trigger('set_account_filter'); },
    company: function(frm) { frm.trigger('set_account_filter'); },
    party_type: function(frm) { frm.trigger('toggle_expense_mode'); },

    set_account_filter: function(frm) {
        if(frm.doc.company && frm.doc.mode_of_payment) {
            let acc_type = "";
            if(["Наличные"].includes(frm.doc.mode_of_payment)) acc_type = "Cash";
            else if(["Пластик", "Терминал", "Перечисления"].includes(frm.doc.mode_of_payment)) acc_type = "Bank";

            if(acc_type) {
                let fields = ['paid_to', 'paid_from'];
                fields.forEach(field => {
                    frm.set_query(field, function() {
                        return { filters: { "company": frm.doc.company, "account_type": acc_type, "is_group": 0 } };
                    });
                });
            }
        }
    },

    toggle_expense_mode: function(frm) {
        if (frm.doc.party_type === 'Expense Category') {
            frm.set_df_property('party', 'label', 'Категория расхода');
            frm.set_df_property('party', 'options', 'Expense Category');
            frm.set_query('party', function() {
                return { filters: { 'company': frm.doc.company } };
            });
        } else {
            frm.set_df_property('party', 'label', 'Party');
            if (['Customer', 'Supplier', 'Employee'].includes(frm.doc.party_type)) {
                frm.set_df_property('party', 'options', frm.doc.party_type);
            }
        }
    },

    party: function(frm) {
        if (frm.doc.party_type === 'Expense Category' && frm.doc.party) {
            frm.set_value('party_name', frm.doc.party);
            frappe.db.get_value('Expense Category', frm.doc.party, 'expense_account', (r) => {
                if (r && r.expense_account) {
                    if(frm.doc.payment_type == "Pay") {
                        frm.set_value('paid_to', r.expense_account);
                        frm.set_value('paid_to_account_currency', 'UZS');
                    }
                    else if(frm.doc.payment_type == "Receive") {
                        frm.set_value('paid_from', r.expense_account);
                    }
                }
            });
        }
    }
});
    """

	frappe.get_doc({
		"doctype": "Client Script",
		"name": script_name,
		"dt": "Payment Entry",
		"enabled": 1,
		"script": js_code
	}).insert(ignore_permissions=True)
	print(f"   ✓ Script yangilandi: {script_name}")
