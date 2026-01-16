/**
 * Stock Entry - Premier Print Custom Logic
 * 
 * Bu fayl quyidagi mantiqlarni o'z ichiga oladi:
 * 1. Sales Order - custom query showing customer_name
 * 2. Sales Order Item - filtered by Sales Order
 * 3. BOM Explosion - Sales Order Item tanlanganda materiallarni yuklash
 * 
 * Faqat "Услуга по заказу" va "Расход по заказу" turlari uchun
 * 
 * @module premierprint/public/js/stock_entry.js
 * @author Premier Print Team
 */

frappe.ui.form.on('Stock Entry', {
    setup: function (frm) {
        // Stock Entry Type FILTER - faqat 2 ta Premier Print turlari
        frm.set_query("stock_entry_type", function () {
            return {
                filters: {
                    'name': ['in', ['Услуги по заказу', 'Расход по заказу']]
                }
            };
        });

        // Sales Order query - show customer name prominently
        frm.set_query("custom_sales_order", function () {
            return {
                query: "premierprint.utils.stock_entry.get_sales_order_query",
                filters: {}
            };
        });

        // Sales Order Item query - FILTER by selected Sales Order
        frm.set_query("custom_sales_order_item", function () {
            let so = frm.doc.custom_sales_order;
            if (!so) {
                frappe.show_alert({
                    message: __('Avval Sales Order tanlang'),
                    indicator: 'orange'
                });
                return { filters: { name: ['=', ''] } };
            }
            return {
                query: "premierprint.utils.stock_entry.get_sales_order_items_query",
                filters: {
                    parent: so,
                    sales_order: so
                }
            };
        });
    },

    refresh: function (frm) {
        // Show/hide Sales Order fields based on stock entry type
        toggle_sales_order_fields(frm);

        // DISABLE link navigation for Sales Order Item (it's a Child Table)
        disable_link_navigation(frm, 'custom_sales_order_item');

        // Add "Load BOM Materials" button if Sales Order Item is selected
        if (frm.doc.custom_sales_order_item && frm.doc.docstatus === 0) {
            frm.add_custom_button(__('BOM dan Materiallarni Yuklash'), function () {
                load_bom_materials(frm);
            }, __('Actions'));
        }
    },

    custom_sales_order: function (frm) {
        // Clear Sales Order Item when Sales Order changes
        if (!frm.doc.custom_sales_order) {
            frm.set_value("custom_sales_order_item", "");
        }
        // Re-apply link navigation disable after field changes
        setTimeout(() => disable_link_navigation(frm, 'custom_sales_order_item'), 300);
    },

    custom_sales_order_item: function (frm) {
        // Re-apply after value changes
        setTimeout(() => disable_link_navigation(frm, 'custom_sales_order_item'), 300);

        // Refresh to show/hide BOM button
        frm.refresh();

        // Auto-load BOM when item selected
        if (frm.doc.custom_sales_order_item && frm.doc.docstatus === 0) {
            frappe.confirm(
                __('Sales Order Item tanlandi. BOM dan materiallarni yuklamoqchimisiz?'),
                function () {
                    load_bom_materials(frm);
                }
            );
        }
    },

    stock_entry_type: function (frm) {
        toggle_sales_order_fields(frm);
    },

    onload: function (frm) {
        toggle_sales_order_fields(frm);
    }
});

// ==================== BOM YUKLASH ====================

/**
 * BOM dan materiallarni yuklash
 */
function load_bom_materials(frm) {
    if (!frm.doc.custom_sales_order_item) {
        frappe.show_alert({
            message: __('Avval Sales Order Item tanlang'),
            indicator: 'orange'
        });
        return;
    }

    frappe.call({
        method: 'premierprint.utils.stock_entry.get_bom_materials',
        args: {
            sales_order_item: frm.doc.custom_sales_order_item
        },
        freeze: true,
        freeze_message: __('BOM materiallarini yuklash...'),
        callback: function (r) {
            if (r.message && r.message.length > 0) {
                if (frm.doc.items && frm.doc.items.length > 0) {
                    frappe.confirm(
                        __('Mavjud elementlarni tozalab, BOM materiallarini qo\'shsinmi?'),
                        function () {
                            frm.clear_table('items');
                            add_bom_items_to_table(frm, r.message);
                        },
                        function () {
                            add_bom_items_to_table(frm, r.message);
                        }
                    );
                } else {
                    add_bom_items_to_table(frm, r.message);
                }
            } else {
                frappe.msgprint({
                    title: __('Ogohlantirish'),
                    message: __('Bu element uchun BOM topilmadi yoki BOM bo\'sh'),
                    indicator: 'orange'
                });
            }
        },
        error: function (r) {
            frappe.msgprint({
                title: __('Xatolik'),
                message: r.message || __('BOM materiallarini yuklashda xatolik'),
                indicator: 'red'
            });
        }
    });
}

/**
 * BOM elementlarini items jadvaliga qo'shish
 */
function add_bom_items_to_table(frm, materials) {
    materials.forEach(function (material) {
        frm.add_child('items', {
            item_code: material.item_code,
            item_name: material.item_name,
            qty: material.qty,
            uom: material.uom,
            stock_uom: material.stock_uom,
            conversion_factor: material.conversion_factor || 1,
            description: material.description,
            s_warehouse: frm.doc.from_warehouse || "",
            t_warehouse: frm.doc.to_warehouse || ""
        });
    });

    frm.refresh_field('items');

    frappe.show_alert({
        message: __(`${materials.length} ta material qo'shildi`),
        indicator: 'green'
    });
}

// ==================== FIELD VISIBILITY ====================

/**
 * Sales Order maydonlarini faqat tegishli turlarda ko'rsatish
 * Faqat "Услуга по заказу" va "Расход по заказу" uchun
 */
function toggle_sales_order_fields(frm) {
    let show_so_fields = ['Услуга по заказу', 'Расход по заказу'].includes(frm.doc.stock_entry_type);

    frm.toggle_display('custom_sales_order', show_so_fields);
    frm.toggle_display('custom_sales_order_item', show_so_fields);
}

// ==================== LINK NAVIGATION FIX ====================

/**
 * Disable link navigation for Child Table fields
 */
function disable_link_navigation(frm, fieldname) {
    let field = frm.fields_dict[fieldname];
    if (!field) return;

    // Hide link button
    if (field.$wrapper) {
        field.$wrapper.find('.link-btn').hide();
        field.$wrapper.addClass('hide-link-btn');
    }

    // Prevent click events
    if (field.$input) {
        field.$wrapper.find('.link-btn').off('click').on('click', function (e) {
            e.preventDefault();
            e.stopPropagation();
            frappe.show_alert({
                message: __('Bu ichki jadval maydoni - alohida sahifa mavjud emas'),
                indicator: 'orange'
            });
            return false;
        });
    }

    // Override open_link method
    if (field.open_link) {
        field.open_link = function () {
            frappe.show_alert({
                message: __('Sales Order Item - bu Child Table. Item Code ustiga bosing.'),
                indicator: 'orange'
            });
        };
    }
}

// ==================== GLOBAL CSS ====================

$(document).ready(function () {
    $('<style>')
        .prop('type', 'text/css')
        .html(`
            .hide-link-btn .link-btn { display: none !important; }
        `)
        .appendTo('head');
});
