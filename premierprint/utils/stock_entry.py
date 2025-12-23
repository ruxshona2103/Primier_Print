import frappe
from frappe import _


@frappe.whitelist()
def get_sales_order_items_query(doctype, txt, searchfield, start, page_len, filters):
	# 1. Filtrlarni olamiz
	sales_order = filters.get("sales_order")

	# Agar Sales Order tanlanmagan bo'lsa, ro'yxat bo'sh
	if not sales_order:
		return []

	# 2. SQL So'rov (Professional)
	# name = Asl ID (Tizim uchun)
	# description = Ekranda ko'rinadigan nom (Odam uchun)
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
	if not sales_order_item_id:
		return []

	# Sales Order Item ma'lumotlarini olamiz
	so_item = frappe.db.get_value("Sales Order Item", sales_order_item_id,
								  ["item_code", "qty", "warehouse"], as_dict=True)

	if not so_item:
		return []

	# Default BOM ni qidiramiz
	bom = frappe.db.get_value("BOM", {"item": so_item.item_code, "is_active": 1, "is_default": 1},
							  "name")

	if not bom:
		frappe.throw(_(f"'{so_item.item_code}' uchun faol BOM (Retsept) topilmadi!"))

	# BOM ni "portlatamiz"
	bom_doc = frappe.get_doc("BOM", bom)
	raw_materials = []

	for item in bom_doc.items:
		# Miqdorni hisoblash
		qty_per_unit = item.qty / bom_doc.quantity
		total_qty = qty_per_unit * so_item.qty

		# Ombor nomiga qarab Cost Center aniqlash
		warehouse = item.source_warehouse or so_item.warehouse
		cost_center = get_cost_center_from_warehouse(warehouse)

		raw_materials.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"description": item.description,
			"qty": total_qty,
			"uom": item.uom,
			"stock_uom": item.stock_uom,
			"conversion_factor": item.conversion_factor,
			"s_warehouse": warehouse,
			"cost_center": cost_center
		})

	return raw_materials


def get_cost_center_from_warehouse(warehouse):
	"""Ombor nomiga qarab Cost Center aniqlash"""
	if not warehouse:
		return None

	warehouse_name = warehouse.lower()

	# Ombor nomida "poli" so'zi bo'lsa -> 100 (Poligrafiya)
	if "poli" in warehouse_name:
		return "100 - Poligrafiya Department"
	# Ombor nomida "reklama" so'zi bo'lsa -> 200 (Reklama)
	elif "reklama" in warehouse_name:
		return "200 - Reklama Department"
	# Ombor nomida "suvenir" so'zi bo'lsa -> 300 (Suvenir)
	elif "suvenir" in warehouse_name:
		return "300 - Suvenir Department"

	# Default
	return "100 - Poligrafiya Department"
