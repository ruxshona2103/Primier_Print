import frappe
from frappe import _


# ==============================================================================
# 1. HELPER FUNCTIONS (Frontend Dropdown va BOM uchun)
# ==============================================================================

@frappe.whitelist()
def get_sales_order_items_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Sales Order Item dropdowni uchun Custom Query.
	ID o'rniga: "Item Name (Item Code)" formatida ko'rsatadi.
	"""
	sales_order = filters.get("sales_order")
	if not sales_order: return []

	return frappe.db.sql("""
        SELECT
            name,
            CONCAT(item_name, ' (', item_code, ')') as description,
            qty
        FROM `tabSales Order Item`
        WHERE parent = %(so)s
        AND (item_name LIKE %(txt)s OR item_code LIKE %(txt)s)
        ORDER BY idx ASC
        LIMIT %(start)s, %(page_len)s
    """, {
		'so': sales_order,
		'txt': f"%{txt}%",
		'start': start,
		'page_len': page_len
	})


@frappe.whitelist()
def get_bom_materials(sales_order_item_id):
	"""
	Sales Order Item tanlanganda, BOM ni "portlatib" xomashyolarni qaytaradi.
	"""
	if not sales_order_item_id: return []

	try:
		# 1. Sales Order Item ma'lumotlari
		so_item = frappe.db.get_value("Sales Order Item", sales_order_item_id,
									  ["item_code", "qty", "warehouse", "parent"], as_dict=True)

		if not so_item or not so_item.item_code: return []

		# 2. Default BOM ni qidirish
		bom_name = frappe.db.get_value("BOM",
									   {"item": so_item.item_code, "is_active": 1, "is_default": 1,
										"docstatus": 1},
									   "name")

		if not bom_name:
			frappe.msgprint(
				_("Mahsulot '{0}' uchun faol BOM topilmadi. Materiallarni qo'lda kiriting.").format(
					so_item.item_code), indicator='blue')
			return []

		# 3. BOM ni hisoblash
		bom_doc = frappe.get_doc("BOM", bom_name)
		raw_materials = []

		for item in bom_doc.items:
			qty_per_unit = item.qty / bom_doc.quantity
			total_qty = qty_per_unit * so_item.qty

			raw_materials.append({
				"item_code": item.item_code,
				"item_name": item.item_name,
				"description": item.description,
				"qty": total_qty,
				"uom": item.uom,
				"stock_uom": item.stock_uom,
				"conversion_factor": item.conversion_factor,
				"s_warehouse": item.source_warehouse or so_item.warehouse
				# Cost Center olib tashlandi (ERPNext default ishlaydi)
			})

		if raw_materials:
			frappe.msgprint(_('{0} ta material BOM dan yuklandi.').format(len(raw_materials)),
							indicator='green')

		return raw_materials

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), f"BOM Error: {sales_order_item_id}")
		return []


# ==============================================================================
# 2. VALIDATSIYA (Saqlashdan oldin tekshirish)
# ==============================================================================

def validate(doc, method):
	"""
	Hujjat saqlanishidan oldin mantiqiy tekshiruvlar.
	Hooks da: 'validate': 'premierprint.premierprint.utils.stock_entry.validate'
	"""

	# Ssenariy 1: Расход по заказу (Chiqim)
	if doc.stock_entry_type == "Расход по заказу":
		if not doc.custom_sales_order:
			frappe.throw(_("Ushbu operatsiya uchun Sales Order tanlash majburiy!"))

	# Ssenariy 2: Услуги по заказу (Xizmat)
	elif doc.stock_entry_type == "Услуги по заказу":
		if not doc.custom_supplier:
			frappe.throw(_("Ushbu operatsiya uchun Supplier tanlash majburiy!"))

	# Ssenariy 3: Перемещение (Transfer)
	elif doc.stock_entry_type == "Перемещение":
		validate_transfer_logic(doc)


def validate_transfer_logic(doc):
	"""Faqat 'Перемещение' uchun maxsus tekshiruvlar"""

	# 1. Kompaniyalar tekshiruvi
	if not doc.company:
		frappe.throw(_("Manba Kompaniya (Company) tanlanmagan!"))
	if not doc.custom_to_sub_company:
		frappe.throw(_("Nishon Kompaniya (To Sub Company) tanlanmagan!"))

	if doc.company == doc.custom_to_sub_company:
		frappe.throw(_("Manba va Nishon kompaniya bir xil bo'lishi mumkin emas!"))

	# 2. Omborlar tekshiruvi (Har bir qator uchun)
	for item in doc.items:
		# Source Warehouse -> Company ga tegishli bo'lishi shart
		if item.s_warehouse:
			s_company = frappe.db.get_value("Warehouse", item.s_warehouse, "company")
			if s_company != doc.company:
				frappe.throw(
					_("Qator {0}: '{1}' ombori '{2}' kompaniyasiga tegishli emas!").format(
						item.idx, item.s_warehouse, doc.company))

		# Target Warehouse -> To Sub Company ga tegishli bo'lishi shart
		if item.t_warehouse:
			t_company = frappe.db.get_value("Warehouse", item.t_warehouse, "company")
			if t_company != doc.custom_to_sub_company:
				frappe.throw(
					_("Qator {0}: '{1}' ombori '{2}' kompaniyasiga tegishli emas!").format(
						item.idx, item.t_warehouse, doc.custom_to_sub_company))


# ==============================================================================
# 3. AVTOMATIZATSIYA (Submit bo'lganda)
# ==============================================================================

def on_submit(doc, method):
	"""
	Submit bo'lganda ishlaydi.
	Hooks da: 'on_submit': 'premierprint.premierprint.utils.stock_entry.on_submit'
	"""
	if doc.stock_entry_type == "Перемещение":
		create_inter_company_docs(doc)


def create_inter_company_docs(doc):
	"""Sales Invoice va Purchase Receipt yaratish"""

	# Manba = Standart Company, Nishon = Custom Field
	source_company = doc.company
	target_company = doc.custom_to_sub_company

	try:
		# A) SALES INVOICE YARATISH (Chiqim)
		# Target Company nomidagi Customerni topamiz
		customer_name = frappe.db.get_value("Customer", {"customer_name": target_company}, "name")

		if not customer_name:
			# Avto-yaratish
			c = frappe.new_doc("Customer")
			c.customer_name = target_company
			c.customer_group = "All Customer Groups"
			c.customer_type = "Company"
			c.insert(ignore_permissions=True)
			customer_name = c.name

		si = frappe.new_doc("Sales Invoice")
		si.company = source_company
		si.customer = customer_name
		si.posting_date = doc.posting_date
		si.set_posting_time = 1

		for item in doc.items:
			si.append("items", {
				"item_code": item.item_code,
				"qty": item.qty,
				"rate": item.basic_rate,
				"warehouse": item.s_warehouse,  # Chiqim ombori
				"cost_center": frappe.db.get_value("Company", source_company, "cost_center")
			})

		si.save(ignore_permissions=True)
		frappe.msgprint(_("Sales Invoice (Draft) yaratildi: {0}").format(si.name),
						indicator='green')

		# B) PURCHASE RECEIPT YARATISH (Kirim)
		# Source Company nomidagi Supplierni topamiz
		supplier_name = frappe.db.get_value("Supplier", {"supplier_name": source_company}, "name")

		if not supplier_name:
			# Avto-yaratish
			s = frappe.new_doc("Supplier")
			s.supplier_name = source_company
			s.supplier_group = "All Supplier Groups"
			s.supplier_type = "Company"
			s.insert(ignore_permissions=True)
			supplier_name = s.name

		pr = frappe.new_doc("Purchase Receipt")
		pr.company = target_company
		pr.supplier = supplier_name
		pr.posting_date = doc.posting_date
		pr.set_posting_time = 1

		for item in doc.items:
			pr.append("items", {
				"item_code": item.item_code,
				"qty": item.qty,
				"rate": item.basic_rate,
				"warehouse": item.t_warehouse,  # Kirim ombori
				"cost_center": frappe.db.get_value("Company", target_company, "cost_center")
			})

		pr.save(ignore_permissions=True)
		frappe.msgprint(_("Purchase Receipt (Draft) yaratildi: {0}").format(pr.name),
						indicator='green')

	except Exception as e:
		frappe.log_error(frappe.get_traceback(), "Inter-Company Auto Creation Error")
		frappe.msgprint(_("Avtomatik hujjatlarni yaratishda xatolik: {0}").format(str(e)),
						indicator='red')
