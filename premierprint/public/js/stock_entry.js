/**
 * ========================================
 * STOCK ENTRY CLIENT SCRIPT - SENIOR LEVEL
 * ========================================
 *
 * Loyiha: premierprint (Frappe v15)
 * Maqsad: Stock Entry uchun 3 xil biznes-logikani UI orqali boshqarish
 *
 * SSENARIYLAR:
 * 1. "Услуги по заказу" (Xizmatlar) - custom_stock_entry_type === "Services"
 * 2. "Расход по заказу" (Sarflar) - custom_stock_entry_type === "Consumption"
 * 3. "Перемещение" (Ko'chirish) - stock_entry_type === "Material Transfer"
 */

frappe.ui.form.on('Stock Entry', {
	/**
	 * ========================================
	 * FORM OCHILGANDA ISHLAYDI
	 * ========================================
	 */
	refresh: function(frm) {
		apply_ui_rules(frm);
	},

	/**
	 * ========================================
	 * STOCK ENTRY TYPE O'ZGARGANDA
	 * ========================================
	 */
	stock_entry_type: function(frm) {
		apply_ui_rules(frm);
	},

	/**
	 * ========================================
	 * CUSTOM STOCK ENTRY TYPE O'ZGARGANDA
	 * ========================================
	 */
	custom_stock_entry_type: function(frm) {
		apply_ui_rules(frm);
	},

	/**
	 * ========================================
	 * SALES ORDER TANLANGANDA
	 * ========================================
	 */
	custom_sales_order: function(frm) {
		// Sales Order Item ni tozalash (yangi Sales Order tanlanganda)
		frm.set_value('custom_sales_order_item', null);

		// Agar Sales Order tanlangan bo'lsa, filtrni yangilash
		if (frm.doc.custom_sales_order) {
			frm.set_query('custom_sales_order_item', function() {
				return {
					query: 'premierprint.utils.stock_entry.get_sales_order_items_query',
					filters: {
						'sales_order': frm.doc.custom_sales_order
					}
				};
			});
		}
	},

	/**
	 * ========================================
	 * SALES ORDER ITEM TANLANGANDA (BOM YUKLASH)
	 * ========================================
	 */
	custom_sales_order_item: function(frm) {
		if (frm.doc.custom_sales_order_item) {
			load_bom_materials(frm);
		}
	},

	/**
	 * ========================================
	 * FROM SUB COMPANY TANLANGANDA
	 * ========================================
	 */
	custom_from_sub_company: function(frm) {
		// Company maydonini avtomatik to'ldirish (Перемещение uchun)
		if (frm.doc.stock_entry_type === 'Перемещение' && frm.doc.custom_from_sub_company) {
			frm.set_value('company', frm.doc.custom_from_sub_company);
		}

		apply_warehouse_filters(frm);
	},

	/**
	 * ========================================
	 * TO SUB COMPANY TANLANGANDA
	 * ========================================
	 */
	custom_to_sub_company: function(frm) {
		apply_warehouse_filters(frm);
	}
});

/**
 * ========================================
 * ITEMS CHILD TABLE EVENTS
 * ========================================
 */
frappe.ui.form.on('Stock Entry Detail', {
	/**
	 * ITEM CODE TANLANGANDA (Перемещение uchun narx avtomatik yuklash)
	 */
	item_code: function(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		// Faqat "Перемещение" tipida Item Price'dan narx olish
		if (frm.doc.stock_entry_type === 'Перемещение' && row.item_code) {
			fetch_item_price(frm, cdt, cdn, row.item_code);
		}
	},

	/**
	 * SOURCE WAREHOUSE (s_warehouse) TANLANGANDA
	 */
	s_warehouse: function(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.s_warehouse) {
			// Cost Center ni avtomatik aniqlash
			frappe.call({
				method: 'premierprint.utils.stock_entry.set_line_cost_center',
				args: {
					warehouse: row.s_warehouse
				},
				callback: function(r) {
					if (r.message && r.message.cost_center) {
						frappe.model.set_value(cdt, cdn, 'cost_center', r.message.cost_center);
					}
				}
			});
		}
	},

	/**
	 * TARGET WAREHOUSE (t_warehouse) TANLANGANDA
	 */
	t_warehouse: function(frm, cdt, cdn) {
		const row = locals[cdt][cdn];

		if (row.t_warehouse) {
			// Agar source warehouse bo'sh bo'lsa, target dan Cost Center olish
			if (!row.s_warehouse) {
				frappe.call({
					method: 'premierprint.utils.stock_entry.set_line_cost_center',
					args: {
						warehouse: row.t_warehouse
					},
					callback: function(r) {
						if (r.message && r.message.cost_center) {
							frappe.model.set_value(cdt, cdn, 'cost_center', r.message.cost_center);
						}
					}
				});
			}
		}
	}
});

/**
 * ========================================
 * MARKAZIY UI BOSHQARISH FUNKSIYASI
 * ========================================
 *
 * Bu funksiya 3 ta ssenariy bo'yicha barcha UI qoidalarini boshqaradi.
 */
function apply_ui_rules(frm) {
	const stock_type = frm.doc.stock_entry_type;
	const custom_type = frm.doc.custom_stock_entry_type;

	// ========================================
	// SSENARIY 1: "Услуги по заказу" (XIZMATLAR)
	// ========================================
	if (custom_type === 'Services') {
		// custom_supplier: KO'RINSIN va MAJBURIY
		frm.set_df_property('custom_supplier', 'hidden', 0);
		frm.set_df_property('custom_supplier', 'reqd', 1);

		// Sales Order maydonlari: KO'RINSIN
		frm.set_df_property('custom_sales_order', 'hidden', 0);
		frm.set_df_property('custom_sales_order_item', 'hidden', 0);

		// FROM/TO Sub Company: YASHIRILSIN
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		// Items jadvalidagi basic_rate: O'ZGARTIRISH MUMKIN
		frm.fields_dict['items'].grid.update_docfield_property(
			'basic_rate', 'read_only', 0
		);

		// Items jadvalidagi basic_rate va amount: KO'RINSIN
		frm.fields_dict['items'].grid.update_docfield_property(
			'basic_rate', 'hidden', 0
		);
		frm.fields_dict['items'].grid.update_docfield_property(
			'amount', 'hidden', 0
		);
	}

	// ========================================
	// SSENARIY 2: "Расход по заказу" (SARFLAR)
	// ========================================
	else if (custom_type === 'Consumption') {
		// custom_supplier: YASHIRILSIN
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);

		// Sales Order maydonlari: KO'RINSIN
		frm.set_df_property('custom_sales_order', 'hidden', 0);
		frm.set_df_property('custom_sales_order_item', 'hidden', 0);

		// FROM/TO Sub Company: YASHIRILSIN
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		// Items jadvalidagi basic_rate va amount: YASHIRILSIN
		frm.fields_dict['items'].grid.update_docfield_property(
			'basic_rate', 'hidden', 1
		);
		frm.fields_dict['items'].grid.update_docfield_property(
			'amount', 'hidden', 1
		);
	}

	// ========================================
	// SSENARIY 3: "Перемещение" (KO'CHIRISH)
	// ========================================
	else if (stock_type === 'Перемещение') {
		// Company maydoni: YASHIRILSIN
		frm.set_df_property('company', 'hidden', 1);

		// Sales Order maydonlari: YASHIRILSIN (Kerak emas)
		frm.set_df_property('custom_sales_order', 'hidden', 1);
		frm.set_df_property('custom_sales_order_item', 'hidden', 1);

		// custom_supplier: YASHIRILSIN
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);

		// FROM/TO Sub Company: KO'RINSIN va MAJBURIY
		frm.set_df_property('custom_from_sub_company', 'hidden', 0);
		frm.set_df_property('custom_to_sub_company', 'hidden', 0);
		frm.set_df_property('custom_from_sub_company', 'reqd', 1);
		frm.set_df_property('custom_to_sub_company', 'reqd', 1);

		// Items jadvalidagi basic_rate va amount: YASHIRILSIN (UI'da ko'rinmasin)
		frm.fields_dict['items'].grid.update_docfield_property(
			'basic_rate', 'hidden', 1
		);
		frm.fields_dict['items'].grid.update_docfield_property(
			'amount', 'hidden', 1
		);

		// Warehouse filtrlash
		apply_warehouse_filters(frm);
	}

	// ========================================
	// DEFAULT HOLAT (Hech narsa tanlanmagan)
	// ========================================
	else {
		// Barcha maydonlarni standart holatga qaytarish
		frm.set_df_property('custom_supplier', 'hidden', 1);
		frm.set_df_property('custom_supplier', 'reqd', 0);
		frm.set_df_property('custom_sales_order', 'hidden', 1);
		frm.set_df_property('custom_sales_order_item', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'hidden', 1);
		frm.set_df_property('custom_to_sub_company', 'hidden', 1);
		frm.set_df_property('custom_from_sub_company', 'reqd', 0);
		frm.set_df_property('custom_to_sub_company', 'reqd', 0);

		// Items jadvalidagi narxlar standart (ko'rinsin)
		frm.fields_dict['items'].grid.update_docfield_property(
			'basic_rate', 'hidden', 0
		);
		frm.fields_dict['items'].grid.update_docfield_property(
			'amount', 'hidden', 0
		);
	}

	// Form ni yangilash (refresh)
	frm.refresh_fields();
}

/**
 * ========================================
 * WAREHOUSE FILTRLASH FUNKSIYASI
 * ========================================
 *
 * Перемещение ssenariysi uchun:
 * - FROM Sub Company tanlansa -> s_warehouse faqat shu kompaniyaga tegishli omborlar
 * - TO Sub Company tanlansa -> t_warehouse faqat shu kompaniyaga tegishli omborlar
 *
 * Filtr logikasi:
 * - Warehouse.company field'i bo'yicha filtrlash (Parent/Child strukturasini qo'llab-quvvatlash)
 */
function apply_warehouse_filters(frm) {
	const from_sub = frm.doc.custom_from_sub_company;
	const to_sub = frm.doc.custom_to_sub_company;

	// ========================================
	// SOURCE WAREHOUSE (s_warehouse) FILTRI
	// ========================================
	if (from_sub) {
		frm.set_query('s_warehouse', 'items', function() {
			return {
				filters: {
					'company': from_sub
				}
			};
		});
	}

	// ========================================
	// TARGET WAREHOUSE (t_warehouse) FILTRI
	// ========================================
	if (to_sub) {
		frm.set_query('t_warehouse', 'items', function() {
			return {
				filters: {
					'company': to_sub
				}
			};
		});
	}
}

/**
 * ========================================
 * OMBOR KALIT SO'ZINI ANIQLASH
 * ========================================
 *
 * Sub Company nomiga qarab ombor qidirish uchun kalit so'z qaytaradi.
 *
 * @param {string} sub_company - Sub Company nomi (masalan: "Poligrafiya")
 * @returns {string} - Qidiruv uchun kalit so'z (masalan: "Poli")
 */
function get_warehouse_keyword(sub_company) {
	const keywords = {
		'Poligrafiya': 'Poli',
		'Reklama': 'Reklama',
		'Suvenir': 'Suvenir'
	};

	// Agar aniq mos kelsa, qaytarish
	if (keywords[sub_company]) {
		return keywords[sub_company];
	}

	// Agar qisman mos kelsa (case-insensitive)
	const sub_lower = (sub_company || '').toLowerCase();

	if (sub_lower.includes('poli')) return 'Poli';
	if (sub_lower.includes('reklama')) return 'Reklama';
	if (sub_lower.includes('suvenir')) return 'Suvenir';

	// Default: Sub Company nomining o'zini qaytarish
	return sub_company;
}

/**
 * ========================================
 * BOM MATERIALLARINI YUKLASH
 * ========================================
 *
 * Sales Order Item tanlanganda, uning BOM materiallarini
 * Stock Entry Items jadvaliga yuklaydi.
 *
 * @param {object} frm - Frappe form object
 */
function load_bom_materials(frm) {
	const so_item_id = frm.doc.custom_sales_order_item;

	if (!so_item_id) {
		frappe.msgprint(__('Iltimos, avval Sales Order Item tanlang.'));
		return;
	}

	// Loading animatsiyasini ko'rsatish
	frappe.dom.freeze(__('BOM materiallari yuklanmoqda...'));

	frappe.call({
		method: 'premierprint.utils.stock_entry.get_bom_materials',
		args: {
			sales_order_item_id: so_item_id
		},
		callback: function(r) {
			frappe.dom.unfreeze();

			if (r.message && r.message.length > 0) {
				// Avvalgi items jadvalini tozalash
				frm.clear_table('items');

				// Har bir BOM materialini jadvalga qo'shish
				r.message.forEach(function(material) {
					const row = frm.add_child('items');

					// Majburiy maydonlar
					row.item_code = material.item_code;
					row.item_name = material.item_name;
					row.description = material.description;
					row.qty = material.qty;
					row.uom = material.uom;
					row.stock_uom = material.stock_uom;
					row.conversion_factor = material.conversion_factor;
					row.s_warehouse = material.s_warehouse;
					row.cost_center = material.cost_center;

					// Ixtiyoriy maydonlar (agar backenddan kelgan bo'lsa)
					if (material.basic_rate) {
						row.basic_rate = material.basic_rate;
					}
					if (material.amount) {
						row.amount = material.amount;
					}
				});

				// Jadvalni yangilash
				frm.refresh_field('items');

				frappe.show_alert({
					message: __('BOM materiallari muvaffaqiyatli yuklandi!'),
					indicator: 'green'
				}, 5);
			} else {
				frappe.msgprint({
					title: __('BOM Topilmadi'),
					message: __('Tanlangan mahsulot uchun faol BOM topilmadi. Items jadvalini qo\'lda to\'ldiring.'),
					indicator: 'orange'
				});
			}
		},
		error: function(r) {
			frappe.dom.unfreeze();

			frappe.msgprint({
				title: __('Xatolik'),
				message: __('BOM materiallarini yuklashda xatolik yuz berdi. Iltimos, qayta urinib ko\'ring.'),
				indicator: 'red'
			});
		}
	});
}

/**
 * ========================================
 * ITEM PRICE'DAN NARX OLISH
 * ========================================
 *
 * Item tanlanganda avtomatik ravishda Item Price masteridan
 * narxni olib kelib, basic_rate maydoniga to'ldiradi.
 *
 * @param {object} frm - Frappe form object
 * @param {string} cdt - Child DocType nomi
 * @param {string} cdn - Child row nomi
 * @param {string} item_code - Item kodi
 */
function fetch_item_price(frm, cdt, cdn, item_code) {
	if (!item_code) {
		return;
	}

	// Item Price'dan narx olish (Selling Price List)
	frappe.call({
		method: 'frappe.client.get_list',
		args: {
			doctype: 'Item Price',
			filters: {
				'item_code': item_code,
				'selling': 1  // Faqat sotish narxi
			},
			fields: ['price_list_rate', 'price_list'],
			order_by: 'modified desc',
			limit: 1
		},
		callback: function(r) {
			if (r.message && r.message.length > 0) {
				const item_price = r.message[0];
				const rate = item_price.price_list_rate || 0;

				// basic_rate ni o'rnatish (UI'da yashirin, lekin backend uchun kerak)
				frappe.model.set_value(cdt, cdn, 'basic_rate', rate);

				// Debug: Console'ga yozish (production'da o'chirish mumkin)
				console.log(`✅ Item Price yuklandi: ${item_code} = ${rate} (${item_price.price_list})`);
			} else {
				// Agar Item Price topilmasa, 0 qo'yish
				frappe.model.set_value(cdt, cdn, 'basic_rate', 0);

				// Foydalanuvchiga ogohlantirish
				frappe.show_alert({
					message: __(`Item Price topilmadi: ${item_code}. Narx 0 ga o'rnatildi.`),
					indicator: 'orange'
				}, 3);

				console.warn(`⚠️ Item Price topilmadi: ${item_code}`);
			}
		},
		error: function(r) {
			// Xatolik bo'lsa, 0 qo'yish
			frappe.model.set_value(cdt, cdn, 'basic_rate', 0);

			console.error(`❌ Item Price olishda xatolik: ${item_code}`, r);
		}
	});
}
