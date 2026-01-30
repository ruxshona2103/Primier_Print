frappe.ui.form.on("Asosiy panel", {
    refresh(frm) {
        frm.trigger("setup_queries");
        frm.trigger("toggle_ui");
    },
    company(frm) {
        frm.trigger("setup_queries");
    },
    operation_type(frm) {
        // Clear all operation-specific fields when type changes
        frm.trigger("clear_operation_fields");
        frm.trigger("toggle_ui");
    },
    clear_operation_fields(frm) {
        // Reset all fields that depend on operation_type
        frm.set_value("sales_order", "");
        frm.set_value("sales_order_item", "");
        frm.set_value("finished_good", "");
        frm.set_value("production_qty", 0);
        frm.set_value("customer", "");
        frm.set_value("supplier", "");
        frm.set_value("target_company", "");
        frm.set_value("target_warehouse", "");
        // Senior Developer Fix: Clear target warehouse fields when operation type changes
        frm.set_value("to_warehouse", "");
    },
    customer(frm) {
        if (frm.doc.customer) {
            frappe.db.get_value("Customer", frm.doc.customer, ["is_internal_customer", "represents_company"], (r) => {
                if (r && r.is_internal_customer) {
                    frm.set_value("target_company", r.represents_company);
                    frm.toggle_display("target_warehouse", true);
                } else {
                    frm.set_value("target_company", "");
                    frm.toggle_display("target_warehouse", false);
                }
                frm.trigger("toggle_ui");
                frm.trigger("setup_queries");
            });
        }
    },
    toggle_ui(frm) {
        // Default hide and un-require all optional fields
        const fields_to_toggle = [
            'customer', 'currency', 'price_list', 'supplier',
            'from_warehouse', 'to_warehouse', 'target_warehouse',
            'purpose', 'finished_good', 'production_qty',
            'sales_order', 'sales_order_item'
        ];
        frm.toggle_display(fields_to_toggle, false);
        frm.toggle_reqd(fields_to_toggle, false);

        // ISSUE 3: Purpose field is completely hidden (never shown)

        if (frm.doc.operation_type) {
            // Delivery Note / Service Sale
            if (['delivery_note', 'service_sale'].includes(frm.doc.operation_type)) {
                frm.toggle_display(['customer', 'currency', 'price_list'], true);
                frm.toggle_reqd(['customer', 'currency', 'price_list'], true);

                // ISSUE 6: target_warehouse ONLY for delivery_note with internal customer
                if (frm.doc.operation_type === 'delivery_note' && frm.doc.target_company) {
                    frm.toggle_display("target_warehouse", true);
                    frm.toggle_reqd("target_warehouse", true);
                }
            }

            // Supplier ONLY for usluga_po_zakasu (service orders)
            if (frm.doc.operation_type === 'usluga_po_zakasu') {
                frm.toggle_display('supplier', true);
                frm.toggle_reqd('supplier', true);
            }

            // Most operations (except service_sale) need from_warehouse
            if (frm.doc.operation_type !== 'service_sale') {
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
            }

            // Material Transfer needs to_warehouse
            if (frm.doc.operation_type === 'material_transfer') {
                frm.toggle_display('to_warehouse', true);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], true);
            }

            // Senior Developer Fix: Hide Target Warehouse for Material Issue to improve UX
            if (frm.doc.operation_type === 'material_issue') {
                frm.toggle_display('to_warehouse', false);
                frm.toggle_display('target_company', false);
                frm.toggle_reqd('to_warehouse', false);
                frm.toggle_reqd('target_company', false);
                // Ensure from_warehouse is shown and mandatory
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
            }

            // ISSUE 1, 2, 4, 5: Sales Order fields for production, rasxod_po_zakasu, usluga_po_zakasu
            if (['production', 'rasxod_po_zakasu', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                frm.toggle_display(['sales_order', 'sales_order_item'], true);
                frm.toggle_reqd('sales_order', true);
            }

            // ISSUE 4 & 5: Production-specific fields
            // Show finished_good and production_qty for operations related to sales orders
            if (['production', 'rasxod_po_zakasu', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                frm.toggle_display(['finished_good', 'production_qty'], true);

                // Only production and usluga_po_zakasu actually produce something
                if (['production', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                    frm.toggle_display('to_warehouse', true);
                    frm.toggle_reqd(['finished_good', 'production_qty', 'from_warehouse', 'to_warehouse'], true);
                } else {
                    // rasxod_po_zakasu: show but don't require
                    frm.toggle_reqd(['finished_good', 'production_qty'], false);
                }
            }
        }
    },
    setup_queries(frm) {
        // Warehouse filters based on company
        if (frm.doc.company) {
            frm.set_query("from_warehouse", () => {
                return { filters: { company: frm.doc.company } };
            });
            frm.set_query("to_warehouse", () => {
                return { filters: { company: frm.doc.company } };
            });
        }
        if (frm.doc.target_company) {
            frm.set_query("target_warehouse", () => {
                return { filters: { company: frm.doc.target_company } };
            });
        }

        // Sales Order query - show customer name (like Stock Entry)
        frm.set_query("sales_order", function () {
            return {
                query: "premierprint.utils.stock_entry.get_sales_order_query",
                filters: {}
            };
        });

        // Sales Order Item query - Use custom function to bypass permissions
        frm.set_query("sales_order_item", function () {
            if (!frm.doc.sales_order) {
                frappe.show_alert({
                    message: __('Please select Sales Order first'),
                    indicator: 'orange'
                });
                return { filters: { name: ['=', ''] } };
            }
            return {
                query: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_so_items",
                filters: {
                    sales_order: frm.doc.sales_order
                }
            };
        });
    },
    sales_order(frm) {
        // Clear sales_order_item and finished_good when sales_order changes (like Stock Entry)
        if (!frm.doc.sales_order) {
            frm.set_value("sales_order_item", "");
        }
        frm.set_value("sales_order_item", "");
        frm.set_value("finished_good", "");
    },
    sales_order_item(frm) {
        // Auto-fetch item_code from Sales Order Item using custom server function
        if (frm.doc.sales_order_item) {
            frappe.call({
                method: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_item_details_from_so_item",
                args: {
                    so_item: frm.doc.sales_order_item
                },
                callback: function (r) {
                    if (r.message) {
                        frm.set_value("finished_good", r.message);
                        frm.refresh_field("finished_good");
                    }
                }
            });
        }
    },
    calculate_totals(frm) {
        let total_qty = 0;
        let total_amount = 0;
        (frm.doc.items || []).forEach(row => {
            total_qty += flt(row.qty);
            total_amount += flt(row.amount);
        });
        frm.set_value("total_quantity", total_qty);
        frm.set_value("total_amount", total_amount);
    }
});

frappe.ui.form.on('Asosiy panel', {
    // Sahifa yuklanganda va Target Company o'zgarganda filtrni yangilaymiz
    refresh: function (frm) {
        frm.trigger('set_warehouse_filters');
    },

    target_company: function (frm) {
        // Target Company o'zgarsa, To Warehouse fieldini tozalaymiz va filtrni yangilaymiz
        frm.set_value('to_warehouse', '');
        frm.trigger('set_warehouse_filters');
    },

    company: function (frm) {
        // Asosiy Company o'zgarsa, From Warehouse filtrini yangilaymiz
        frm.set_value('from_warehouse', '');
        frm.trigger('set_warehouse_filters');
    },

    set_warehouse_filters: function (frm) {
        // 1. "From Warehouse" filtrini o'rnatish (Asosiy Company bo'yicha)
        frm.set_query('from_warehouse', function () {
            return {
                filters: {
                    'company': frm.doc.company,
                    'is_group': 0 // Guruh bo'lmagan, real omborlar chiqsin
                }
            };
        });

        // 2. "To Warehouse" filtrini o'rnatish (Target Company bo'yicha)
        if (frm.doc.target_company) {
            frm.set_query('to_warehouse', function () {
                return {
                    filters: {
                        'company': frm.doc.target_company,
                        'is_group': 0
                    }
                };
            });
        }
    }
});

// Child Table: Asosiy panel item
frappe.ui.form.on('Asosiy panel item', {
    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code) {
            // Fetch item details including is_stock_item
            frappe.db.get_value('Item', row.item_code, ['item_name', 'is_stock_item', 'stock_uom'], (r) => {
                if (r) {
                    frappe.model.set_value(cdt, cdn, 'item_name', r.item_name);
                    frappe.model.set_value(cdt, cdn, 'is_stock_item', r.is_stock_item);
                    if (!row.uom) {
                        frappe.model.set_value(cdt, cdn, 'uom', r.stock_uom);
                    }
                }
            });
        }
    },
    qty: function (frm, cdt, cdn) {
        calculate_row_amount(frm, cdt, cdn);
        frm.trigger('calculate_totals');
    },
    rate: function (frm, cdt, cdn) {
        calculate_row_amount(frm, cdt, cdn);
        frm.trigger('calculate_totals');
    },
    items_remove: function (frm) {
        frm.trigger('calculate_totals');
    }
});

function calculate_row_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let amount = flt(row.qty) * flt(row.rate);
    frappe.model.set_value(cdt, cdn, 'amount', amount);
}