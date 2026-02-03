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
                    // Auto-set Inter-Company Price List for internal customers
                    frm.trigger("set_inter_company_price_list");
                } else {
                    frm.set_value("target_company", "");
                    frm.toggle_display("target_warehouse", false);
                    // Allow manual price_list selection for non-internal customers
                    frm.set_df_property("price_list", "read_only", 0);
                }
                frm.trigger("toggle_ui");
                frm.trigger("setup_queries");
            });
        } else {
            // Customer cleared - reset price_list and allow manual selection
            frm.set_value("target_company", "");
            frm.set_df_property("price_list", "read_only", 0);
            frm.trigger("toggle_ui");
        }
    },
    set_inter_company_price_list(frm) {
        // Check if Inter-Company Price List exists and set it automatically
        const INTER_COMPANY_PRICE_LIST = "Inter-Company Price List";
        
        frappe.db.exists("Price List", INTER_COMPANY_PRICE_LIST).then(exists => {
            if (exists) {
                frm.set_value("price_list", INTER_COMPANY_PRICE_LIST);
                // Make price_list read-only for internal customers
                frm.set_df_property("price_list", "read_only", 1);
                frappe.show_alert({
                    message: __("Inter-Company Price List avtomatik tanlandi"),
                    indicator: 'green'
                }, 3);
            } else {
                // Price List does not exist - show error message
                frappe.msgprint({
                    title: __("Price List Topilmadi"),
                    message: __("Iltimos, Price Listlar ichida <b>'Inter-Company Price List'</b> nomli narxnomani yarating va unda <b>'Buying'</b> hamda <b>'Selling'</b> galochkalarini yoqing."),
                    indicator: 'red'
                });
                // Clear the price_list and allow manual entry as fallback
                frm.set_value("price_list", "");
                frm.set_df_property("price_list", "read_only", 0);
            }
        });
    },
    toggle_ui(frm) {
        // Default hide and un-require all optional fields
        const fields_to_toggle = [
            'customer', 'currency', 'price_list', 'supplier',
            'from_warehouse', 'to_warehouse', 'target_warehouse', 'target_company',
            'purpose', 'finished_good', 'production_qty',
            'sales_order', 'sales_order_item'
        ];
        frm.toggle_display(fields_to_toggle, false);
        frm.toggle_reqd(fields_to_toggle, false);

        if (frm.doc.operation_type) {
            // ============================================================
            // DELIVERY NOTE LOGIC - Full Inter-Company Support
            // ============================================================
            if (frm.doc.operation_type === 'delivery_note') {
                // Always show customer, currency, price_list, from_warehouse
                frm.toggle_display(['customer', 'currency', 'price_list', 'from_warehouse'], true);
                frm.toggle_reqd(['customer', 'currency', 'price_list', 'from_warehouse'], true);
                
                // Show target_company (read-only, auto-filled from internal customer)
                frm.toggle_display('target_company', true);
                
                // target_warehouse ONLY shown when internal customer is selected
                if (frm.doc.target_company) {
                    frm.toggle_display('target_warehouse', true);
                    frm.toggle_reqd('target_warehouse', true);
                }
            }

            // ============================================================
            // SERVICE SALE LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'service_sale') {
                frm.toggle_display(['customer', 'currency', 'price_list'], true);
                frm.toggle_reqd(['customer', 'currency', 'price_list'], true);
                // No warehouse needed for service sale
            }

            // ============================================================
            // SUPPLIER LOGIC - For production, usluga_po_zakasu, purchase_request
            // ============================================================
            if (['production', 'usluga_po_zakasu', 'purchase_request'].includes(frm.doc.operation_type)) {
                frm.toggle_display('supplier', true);
                // Supplier is optional (not mandatory) - can be used for reference
                frm.toggle_reqd('supplier', false);
            }

            // ============================================================
            // MATERIAL TRANSFER LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'material_transfer') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], true);
            }

            // ============================================================
            // MATERIAL ISSUE LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'material_issue') {
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
                // No to_warehouse for Material Issue
            }

            // ============================================================
            // PURCHASE REQUEST LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'purchase_request') {
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
            }

            // ============================================================
            // PRODUCTION HUB: Sales Order related operations
            // ============================================================
            if (['production', 'rasxod_po_zakasu', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                // All 3 need Sales Order link
                frm.toggle_display(['sales_order', 'sales_order_item'], true);
                frm.toggle_reqd('sales_order', true);
                // Show finished_good and production_qty
                frm.toggle_display(['finished_good', 'production_qty'], true);
            }

            // usluga_po_zakasu - Service costs only, NO warehouses needed
            if (frm.doc.operation_type === 'usluga_po_zakasu') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], false);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], false);
                frm.toggle_reqd(['finished_good', 'production_qty'], true);
            }

            // rasxod_po_zakasu - Material Transfer to WIP
            if (frm.doc.operation_type === 'rasxod_po_zakasu') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], true);
                // Auto-default to WIP warehouse
                if (!frm.doc.to_warehouse && frm.doc.company) {
                    frm.trigger('set_wip_warehouse_default');
                }
            }

            // production - The Aggregator
            if (frm.doc.operation_type === 'production') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['finished_good', 'production_qty', 'from_warehouse', 'to_warehouse'], true);
            }
        }
    },
    set_wip_warehouse_default(frm) {
        // Set default WIP warehouse for rasxod_po_zakasu operation
        if (frm.doc.operation_type === 'rasxod_po_zakasu' && frm.doc.company && !frm.doc.to_warehouse) {
            // Search for WIP warehouse in the company
            frappe.db.get_value('Warehouse', 
                {
                    'company': frm.doc.company,
                    'warehouse_name': ['like', '%Work In Progress%']
                }, 
                'name'
            ).then(r => {
                if (r && r.message && r.message.name) {
                    frm.set_value('to_warehouse', r.message.name);
                } else {
                    // Try alternative naming convention
                    frappe.db.get_value('Warehouse', 
                        {
                            'company': frm.doc.company,
                            'warehouse_name': ['like', '%WIP%']
                        }, 
                        'name'
                    ).then(r2 => {
                        if (r2 && r2.message && r2.message.name) {
                            frm.set_value('to_warehouse', r2.message.name);
                        }
                    });
                }
            });
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

        // Supplier filter - show only active (enabled) suppliers
        frm.set_query("supplier", () => {
            return {
                filters: {
                    'disabled': 0
                }
            };
        });

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