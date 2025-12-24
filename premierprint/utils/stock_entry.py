import frappe
from frappe import _


@frappe.whitelist()
def get_sales_order_items_query(doctype, txt, searchfield, start, page_len, filters):
	"""
	Sales Order Item uchun link field query

	Args:
		doctype: Sales Order Item
		txt: Qidiruv matni
		searchfield: Qidiruv maydon nomi
		start: Sahifalash boshlang'ich indeksi
		page_len: Sahifa hajmi
		filters: {'sales_order': 'SO-00001'}

	Returns:
		List of tuples: [(name, description, qty), ...]
	"""
	sales_order = filters.get("sales_order")

	# Agar Sales Order tanlanmagan bo'lsa, bo'sh ro'yxat qaytarish
	if not sales_order:
		return []

	# Sales Order mavjudligini tekshirish
	if not frappe.db.exists("Sales Order", sales_order):
		frappe.throw(_("Sales Order '{0}' topilmadi!").format(sales_order))

	# SQL so'rov (CONCAT bilan odam tushunadigan nom yaratish)
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
	Sales Order Item dan BOM ni explosion qilish

	Args:
		sales_order_item_id: Sales Order Item ID (Qaysi mahsulot uchun BOM kerak)

	Returns:
		List[dict]: BOM explosion natijalari (xomashyolar ro'yxati)

	Raises:
		frappe.DoesNotExistError: Sales Order Item topilmasa
		frappe.ValidationError: BOM topilmasa
	"""
	if not sales_order_item_id:
		frappe.throw(_("Sales Order Item ID ko'rsatilmagan!"))

	# 1. Sales Order Item ma'lumotlarini olish
	so_item = frappe.db.get_value(
		"Sales Order Item",
		sales_order_item_id,
		["item_code", "qty", "warehouse"],
		as_dict=True
	)

	if not so_item:
		frappe.throw(_("Sales Order Item '{0}' topilmadi!").format(sales_order_item_id))

	# 2. Item uchun faol va default BOM topish
	bom_name = get_default_bom(so_item.item_code)

	if not bom_name:
		frappe.throw(
			_("'{0}' uchun faol va default BOM (Retsept) topilmadi! Iltimos, avval BOM yarating.").format(
				so_item.item_code
			)
		)

	# 3. BOM ni explosion qilish
	return explode_bom(bom_name, so_item.qty, so_item.warehouse)


def get_default_bom(item_code):
	"""
	Item uchun default BOM topish

	Args:
		item_code: Item kodi

	Returns:
		str: BOM name yoki None
	"""
	return frappe.db.get_value(
		"BOM",
		{
			"item": item_code,
			"is_active": 1,
			"is_default": 1,
			"docstatus": 1  # Faqat submitted BOM
		},
		"name"
	)


def explode_bom(bom_name, required_qty, default_warehouse=None):
	"""
	BOM ni explosion qilish (xomashyolarni miqdor bilan hisoblash)

	Args:
		bom_name: BOM nomi
		required_qty: Kerakli miqdor (nechta tayyor mahsulot)
		default_warehouse: Default ombor (agar BOM da ko'rsatilmagan bo'lsa)

	Returns:
		List[dict]: Xomashyolar ro'yxati
	"""
	try:
		bom_doc = frappe.get_doc("BOM", bom_name)
	except frappe.DoesNotExistError:
		frappe.throw(_("BOM '{0}' topilmadi!").format(bom_name))

	raw_materials = []

	for bom_item in bom_doc.items:
		# Bitta tayyor mahsulot uchun kerakli xomashyo miqdori
		qty_per_unit = bom_item.qty / bom_doc.quantity

		# Umumiy kerakli xomashyo miqdori
		total_qty = qty_per_unit * required_qty

		# Ombor aniqlash (BOM da ko'rsatilgan yoki default)
		warehouse = bom_item.source_warehouse or default_warehouse

		# Cost Center avtomatik aniqlash
		cost_center = get_cost_center_from_warehouse(warehouse)

		# Xomashyo ma'lumotlarini qo'shish
		raw_materials.append({
			"item_code": bom_item.item_code,
			"item_name": bom_item.item_name,
			"description": bom_item.description,
			"qty": total_qty,
			"uom": bom_item.uom,
			"stock_uom": bom_item.stock_uom,
			"conversion_factor": bom_item.conversion_factor,
			"s_warehouse": warehouse,
			"cost_center": cost_center
		})

	return raw_materials


def get_cost_center_from_warehouse(warehouse):
	"""
	Ombor nomiga qarab Cost Center aniqlash

	Business Logic:
		- "Poli" so'zi bo'lsa → 100 - Poligrafiya Department
		- "Reklama" so'zi bo'lsa → 200 - Reklama Department
		- "Suvenir" so'zi bo'lsa → 300 - Suvenir Department
		- Default → 100 - Poligrafiya Department

	Args:
		warehouse: Ombor nomi

	Returns:
		str: Cost Center nomi
	"""
	if not warehouse:
		return "100 - Poligrafiya Department"  # Default

	warehouse_lower = warehouse.lower()

	# Ombor nomidan Cost Center aniqlash
	if "poli" in warehouse_lower:
		return "100 - Poligrafiya Department"
	elif "reklama" in warehouse_lower:
		return "200 - Reklama Department"
	elif "suvenir" in warehouse_lower:
		return "300 - Suvenir Department"

	# Default Cost Center
	return "100 - Poligrafiya Department"
