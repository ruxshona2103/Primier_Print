import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def run():
	"""
	Stock Entry uchun barcha Custom Field va Stock Entry Type larni yaratadi.
	Ishlatish: bench execute premierprint.setup_stock.run
	"""
	print("=" * 80)
	print("STOCK ENTRY TIKLASH BOSHLANDI...")
	print("=" * 80)

	create_custom_fields_for_stock_entry()
	create_stock_entry_types()
	create_client_script()

	# Frappe cache ni tozalash
	frappe.db.commit()
	frappe.clear_cache()

	print("\n" + "=" * 80)
	print("✓ TIKLASH MUVAFFAQIYATLI TUGALLANDI!")
	print("Keyingi qadam: bench migrate")
	print("=" * 80)


def create_custom_fields_for_stock_entry():
	"""Stock Entry uchun Custom Fields yaratish"""
	print("\n[1/2] Custom Fields yaratilmoqda...")

	custom_fields = {
		"Stock Entry": [
			# 1. Supplier (Taminotchi) - Услуги по заказу uchun
			{
				"fieldname": "custom_supplier",
				"label": "Supplier",
				"fieldtype": "Link",
				"options": "Supplier",
				"insert_after": "stock_entry_type",
				"reqd": 0,
				"hidden": 0,
				"read_only": 0,
				"description": "Услуги по заказу uchun taminotchi"
			},
			# 2. From Sub Company - Ko'chirish uchun
			{
				"fieldname": "custom_from_sub_company",
				"label": "From Sub Company",
				"fieldtype": "Select",
				"options": "\nПолиграфия\nРеклама\nСувенир",
				"insert_after": "custom_supplier",
				"reqd": 0,
				"hidden": 0,
				"read_only": 0,
				"description": "Qaysi tashkilotdan ko'chiriladi"
			},
			# 3. To Sub Company - Ko'chirish uchun
			{
				"fieldname": "custom_to_sub_company",
				"label": "To Sub Company",
				"fieldtype": "Select",
				"options": "\nПолиграфия\nРеклама\nСувенир",
				"insert_after": "custom_from_sub_company",
				"reqd": 0,
				"hidden": 0,
				"read_only": 0,
				"description": "Qaysi tashkilotga ko'chiriladi"
			},
			# 4. Sales Order - Buyurtma
			{
				"fieldname": "custom_sales_order",
				"label": "Sales Order",
				"fieldtype": "Link",
				"options": "Sales Order",
				"insert_after": "custom_to_sub_company",
				"reqd": 0,
				"hidden": 0,
				"read_only": 0,
				"description": "Buyurtma raqami"
			},
			# 5. Sales Order Item - Buyurtma mahsuloti
			{
				"fieldname": "custom_sales_order_item",
				"label": "Sales Order Item",
				"fieldtype": "Link",
				"options": "Sales Order Item",
				"insert_after": "custom_sales_order",
				"reqd": 0,
				"hidden": 0,
				"read_only": 0,
				"description": "Buyurtmadan mahsulot tanlash",
				"get_query": "premierprint.utils.stock_entry.get_sales_order_items_query"
			}
		]
	}

	# Custom Fields yaratish
	create_custom_fields(custom_fields, update=True)
	print("   ✓ Custom Fields yaratildi: 5 ta maydon")


def create_stock_entry_types():
	"""Stock Entry Type larni yaratish"""
	print("\n[2/2] Stock Entry Types yaratilmoqda...")

	types_data = [
		{
			"name": "Услуги по заказу",
			"purpose": "Material Issue",
			"description": "Buyurtma bo'yicha xizmatlar (Narx ko'rinadi)"
		},
		{
			"name": "Расход по заказу",
			"purpose": "Material Issue",
			"description": "Buyurtma bo'yicha chiqim (Narx yashiriladi)"
		},
		{
			"name": "Перемещение",
			"purpose": "Material Transfer",
			"description": "Tashkilotlar o'rtasida ko'chirish"
		}
	]

	created_count = 0
	skipped_count = 0

	for type_data in types_data:
		if frappe.db.exists("Stock Entry Type", type_data["name"]):
			# Mavjud bo'lsa - o'tkazib yuborish (Purpose o'zgartirib bo'lmaydi)
			skipped_count += 1
			print(f"   ⊙ Mavjud (o'tkazildi): {type_data['name']}")
		else:
			# Yangi yaratish
			doc = frappe.new_doc("Stock Entry Type")
			doc.name = type_data["name"]
			doc.purpose = type_data["purpose"]
			doc.insert(ignore_permissions=True)
			created_count += 1
			print(f"   ✓ Yaratildi: {type_data['name']}")

	print(f"   Jami: {created_count} ta yaratildi, {skipped_count} ta mavjud")


def create_client_script():
	"""Stock Entry uchun Client Script yaratish"""
	print("\n[3/3] Client Script yaratilmoqda...")

	script_name = "Stock Entry - Custom Logic"

	# JavaScript kodi
	script_code = """
frappe.ui.form.on('Stock Entry', {
	onload: function(frm) {
		// Stock Entry Type ni filtrlash (Faqat kerakli 3 ta)
		frm.set_query('stock_entry_type', function() {
			return {
				filters: {
					'name': ['in', ['Услуги по заказу', 'Расход по заказу', 'Перемещение']]
				}
			};
		});
	},

	refresh: function(frm) {
		// Har safar ochilganda UI rules ni qo'llash
		apply_ui_rules(frm);
	},

	stock_entry_type: function(frm) {
		// Type o'zgarganda UI rules ni qo'llash
		apply_ui_rules(frm);
	},

	custom_sales_order: function(frm) {
		// Sales Order o'zgarganda Sales Order Item ni tozalash
		frm.set_value('custom_sales_order_item', '');

		// Sales Order Item uchun query filtri
		if (frm.doc.custom_sales_order) {
			frm.set_query('custom_sales_order_item', function() {
				return {
					query: 'premierprint.utils.stock_entry.get_sales_order_items_query',
					filters: {
						sales_order: frm.doc.custom_sales_order
					}
				};
			});
		}
	},

	custom_sales_order_item: function(frm) {
		// Sales Order Item tanlanganda BOM materiallarini yuklash
		if (frm.doc.custom_sales_order_item) {
			frappe.call({
				method: 'premierprint.utils.stock_entry.get_bom_materials',
				args: {
					sales_order_item_id: frm.doc.custom_sales_order_item
				},
				callback: function(r) {
					if (r.message) {
						// Avvalgi itemlarni tozalash
						frm.clear_table('items');

						// Yangi materiallarni qo'shish
						r.message.forEach(function(item) {
							let row = frm.add_child('items');
							row.item_code = item.item_code;
							row.item_name = item.item_name;
							row.description = item.description;
							row.qty = item.qty;
							row.uom = item.uom;
							row.stock_uom = item.stock_uom;
							row.conversion_factor = item.conversion_factor;
							row.s_warehouse = item.s_warehouse;
							row.cost_center = item.cost_center;
						});

						frm.refresh_field('items');

						// Warehouse o'zgarganda Cost Center avtomatik qo'yish
						setup_warehouse_change_handler(frm);
					}
				}
			});
		}
	}
});

// Items jadvalida warehouse o'zgarganda
frappe.ui.form.on('Stock Entry Detail', {
	s_warehouse: function(frm, cdt, cdn) {
		auto_set_cost_center(frm, cdt, cdn, 's_warehouse');
	},

	t_warehouse: function(frm, cdt, cdn) {
		auto_set_cost_center(frm, cdt, cdn, 't_warehouse');
	}
});

function apply_ui_rules(frm) {
	const entry_type = frm.doc.stock_entry_type;

	if (entry_type === 'Услуги по заказу') {
		// A) Услуги по заказу - Narx ko'rinadi va o'zgartiriladi

		// Supplier maydoni - Ko'rinsin va majburiy
		frm.set_df_property('custom_supplier', 'hidden', 0);
		frm.set_df_property('custom_supplier', 'reqd', 1);

		// From/To Sub Company - Yashirilsin
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		// Items jadvalida narx (basic_rate) - Ko'rinsin va o'zgartirilsin
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'read_only', 0);
		frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('valuation_rate', 'hidden', 0);

		// Asosiy formdagi summa maydonlari - Ko'rinsin
		frm.set_df_property('total_outgoing_value', 'hidden', 0);
		frm.set_df_property('total_incoming_value', 'hidden', 0);
		frm.set_df_property('total_amount', 'hidden', 0);
		frm.set_df_property('value_difference', 'hidden', 0);

	} else if (entry_type === 'Расход по заказу') {
		// B) Расход по заказу - Narx butunlay yashiriladi

		// Supplier - Yashirilsin
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);

		// From/To Sub Company - Yashirilsin
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		// Items jadvalida narx (basic_rate, amount, valuation_rate) - BUTUNLAY YASHIRILSIN
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 1);
		frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 1);
		frm.fields_dict.items.grid.update_docfield_property('valuation_rate', 'hidden', 1);

		// Asosiy formdagi summa maydonlari - BUTUNLAY YASHIRILSIN
		frm.set_df_property('total_outgoing_value', 'hidden', 1);
		frm.set_df_property('total_incoming_value', 'hidden', 1);
		frm.set_df_property('total_amount', 'hidden', 1);
		frm.set_df_property('value_difference', 'hidden', 1);

	} else if (entry_type === 'Перемещение') {
		// C) Перемещение - Narx ko'rinadi lekin o'zgartirib bo'lmaydi

		// Supplier - Yashirilsin
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);

		// From/To Sub Company - Ko'rinsin va majburiy
		frm.set_df_property('custom_from_sub_company', 'hidden', 0);
		frm.set_df_property('custom_to_sub_company', 'hidden', 0);
		frm.set_df_property('custom_from_sub_company', 'reqd', 1);
		frm.set_df_property('custom_to_sub_company', 'reqd', 1);

		// Items jadvalida narx (basic_rate) - Ko'rinsin lekin o'zgarmasin (READ ONLY)
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'read_only', 1);
		frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('valuation_rate', 'hidden', 0);

		// Asosiy formdagi summa maydonlari - Ko'rinsin lekin o'zgarmasin
		frm.set_df_property('total_outgoing_value', 'hidden', 0);
		frm.set_df_property('total_incoming_value', 'hidden', 0);
		frm.set_df_property('total_amount', 'hidden', 0);
		frm.set_df_property('value_difference', 'hidden', 0);

	} else {
		// D) Boshqa turlar uchun - Default holatga qaytarish
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('basic_rate', 'read_only', 0);
		frm.fields_dict.items.grid.update_docfield_property('amount', 'hidden', 0);
		frm.fields_dict.items.grid.update_docfield_property('valuation_rate', 'hidden', 0);

		// Asosiy formdagi summa maydonlari - Ko'rinsin
		frm.set_df_property('total_outgoing_value', 'hidden', 0);
		frm.set_df_property('total_incoming_value', 'hidden', 0);
		frm.set_df_property('total_amount', 'hidden', 0);
		frm.set_df_property('value_difference', 'hidden', 0);
	}

	frm.refresh_field('items');
}

function setup_warehouse_change_handler(frm) {
	// Items jadvalida warehouse o'zgarganda Cost Center avtomatik qo'yish
	frm.fields_dict.items.grid.grid_rows.forEach(function(row) {
		if (row.doc) {
			auto_set_cost_center_from_warehouse(row.doc);
		}
	});
}

function auto_set_cost_center(frm, cdt, cdn, warehouse_field) {
	let row = locals[cdt][cdn];
	auto_set_cost_center_from_warehouse(row);
	frm.refresh_field('items');
}

function auto_set_cost_center_from_warehouse(row) {
	// S_warehouse yoki T_warehouse dan Cost Center aniqlash
	let warehouse = row.s_warehouse || row.t_warehouse;

	if (warehouse) {
		let warehouse_lower = warehouse.toLowerCase();

		// Ombor nomida "poli" so'zi bo'lsa -> 100
		if (warehouse_lower.includes('poli')) {
			row.cost_center = '100 - Poligrafiya Department';
		}
		// Ombor nomida "reklama" so'zi bo'lsa -> 200
		else if (warehouse_lower.includes('reklama')) {
			row.cost_center = '200 - Reklama Department';
		}
		// Ombor nomida "suvenir" so'zi bo'lsa -> 300
		else if (warehouse_lower.includes('suvenir')) {
			row.cost_center = '300 - Suvenir Department';
		}
		// Default
		else {
			row.cost_center = '100 - Poligrafiya Department';
		}
	}
}
"""

	# Client Script mavjudligini tekshirish
	if frappe.db.exists("Client Script", script_name):
		# Yangilash
		doc = frappe.get_doc("Client Script", script_name)
		doc.script = script_code
		doc.save(ignore_permissions=True)
		print(f"   ↻ Yangilandi: {script_name}")
	else:
		# Yangi yaratish
		doc = frappe.new_doc("Client Script")
		doc.name = script_name
		doc.dt = "Stock Entry"
		doc.enabled = 1
		doc.script_type = "Form"
		doc.script = script_code
		doc.insert(ignore_permissions=True)
		print(f"   ✓ Yaratildi: {script_name}")
