import frappe
from frappe import _


@frappe.whitelist()
def get_sales_order_items_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Sales Order Itemlarini filtrlash (ID o'rniga chiroyli nom ko'rsatish).
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
	BOM ni portlatish (Explode).
	"""
	if not sales_order_item_id: return []

	try:
		# 1. Ma'lumot olish
		so_item = frappe.db.get_value("Sales Order Item", sales_order_item_id,
									  ["item_code", "qty", "warehouse", "parent"], as_dict=True)

		if not so_item or not so_item.item_code: return []

		# 2. BOM qidirish
		bom_name = frappe.db.get_value("BOM",
									   {"item": so_item.item_code, "is_active": 1, "is_default": 1,
										"docstatus": 1},
									   "name"
									   )

		if not bom_name:
			# Xato otmaymiz, shunchaki xabar beramiz
			frappe.msgprint(_("Mahsulot '{0}' uchun BOM topilmadi.").format(so_item.item_code),
							indicator='blue')
			return []

		# 3. Portlatish
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
				# Cost Center olib tashlandi!
			})

		if raw_materials:
			frappe.msgprint(_('{0} ta material BOM dan yuklandi.').format(len(raw_materials)),
							indicator='green')

		return raw_materials

	except Exception as e:
		frappe.log_error(f"BOM Error: {str(e)}")
		return []


# --- AVTOMATIZATSIYA (Перемещение) ---

def on_submit(doc, method):
	"""
	Stock Entry Submit bo'lganda ishlaydi.
	"""
	if doc.stock_entry_type == "Перемещение":
		if not doc.custom_to_sub_company:
			frappe.throw(_("Nishon kompaniya (To Sub Company) tanlanmagan!"))

		create_inter_company_docs(doc)


def create_inter_company_docs(doc):
	source_company = doc.company
	target_company = doc.custom_to_sub_company

	# 1. SALES INVOICE (Chiqim)
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
	si.posting_time = doc.posting_time

	for item in doc.items:
		si.append("items", {
			"item_code": item.item_code,
			"qty": item.qty,
			"rate": item.basic_rate,
			"warehouse": item.s_warehouse
			# Cost Center: Tizim o'zi Company/Item dan oladi
		})

	si.save(ignore_permissions=True)
	frappe.msgprint(_(f"Sales Invoice (Draft) yaratildi: {si.name}"), indicator='green')

	# 2. PURCHASE RECEIPT (Kirim)
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
	pr.posting_time = doc.posting_time

	for item in doc.items:
		pr.append("items", {
			"item_code": item.item_code,
			"qty": item.qty,
			"rate": item.basic_rate,
			"warehouse": item.t_warehouse
		})

	pr.save(ignore_permissions=True)
	frappe.msgprint(_(f"Purchase Receipt (Draft) yaratildi: {pr.name}"), indicator='green')
