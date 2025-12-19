import frappe


@frappe.whitelist()
def get_sales_order_item_details(sales_order, item_code):
	"""
	Sales Order Item tanlanganda, uning BOM ni topib, xomashyolarni qaytaradi.
	"""
	if not sales_order or not item_code:
		return []

	# 1. Sales Orderdagi o'sha itemni topamiz
	so_item = frappe.db.get_value("Sales Order Item",
								  {"parent": sales_order, "item_code": item_code},
								  ["name", "qty"], as_dict=True)

	if not so_item:
		return []

	# 2. BOM ni qidiramiz
	bom = frappe.db.get_value("BOM", {"item": item_code, "is_active": 1, "is_default": 1}, "name")

	if not bom:
		frappe.throw(f"{item_code} uchun faol BOM topilmadi!")

	# 3. BOM ni "portlatamiz" (Explode) - xomashyolarni olamiz
	bom_doc = frappe.get_doc("BOM", bom)
	raw_materials = []

	for item in bom_doc.items:
		raw_materials.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"qty": item.qty * so_item.qty,  # Jami kerakli miqdor
			"uom": item.uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": item.conversion_factor,
			"s_warehouse": item.source_warehouse,  # Xomashyo ombori
			"t_warehouse": "",  # Ishlatilayotgani uchun bo'sh bo'lishi mumkin
			"expense_account": "Cost of Goods Sold - PP"  # Yoki sening hisobing
		})

	return raw_materials
