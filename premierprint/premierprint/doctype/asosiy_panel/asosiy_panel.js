// Operation Type Mapping (Russian → Purpose)
// Запрос материалов → Material Request (Purchase)
// Приход на склад → Purchase Receipt
// Списание материалов → Stock Entry (Material Issue)
// Перемещения → Stock Entry (Material Transfer)
// Отгрузка товаров → Delivery Note (+ Inter-company)
// Расход по заказу → Material Transfer to WIP
// Услуги по заказу → Service cost logging
// Производство → Repack Stock Entry (Aggregator)

frappe.ui.form.on("Asosiy panel", {
    refresh(frm) {
        frm.trigger("setup_queries");
        frm.trigger("toggle_ui");
    },
    company(frm) {
        frm.trigger("setup_queries");
        // Clear warehouses when company changes and reset defaults
        frm.set_value('from_warehouse', '');
        frm.set_value('to_warehouse', '');
        // Re-apply warehouse defaults based on operation type
        if (frm.doc.operation_type === 'Расход по заказу') {
            frm.trigger('set_wip_warehouse_default');
        } else if (frm.doc.operation_type === 'Производство') {
            frm.trigger('set_production_warehouses');
        }
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
            'finished_good', 'production_qty',
            'sales_order', 'sales_order_item'
        ];
        frm.toggle_display(fields_to_toggle, false);
        frm.toggle_reqd(fields_to_toggle, false);

        // Reset label back to default for non-purchase_receipt
        frm.set_df_property('from_warehouse', 'label', __('From Warehouse'));

        // Reset mandatory flags (explicitly via df_property as requested)
        frm.set_df_property('supplier', 'reqd', 0);
        frm.set_df_property('from_warehouse', 'reqd', 0);

        if (frm.doc.operation_type) {
            // ============================================================
            // DELIVERY NOTE LOGIC - Full Inter-Company Support
            // ============================================================
            if (frm.doc.operation_type === 'Отгрузка товаров') {
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
            if (frm.doc.operation_type === 'service_sale') { // NOTE: service_sale not in Russian mapping
                frm.toggle_display(['customer', 'currency', 'price_list'], true);
                frm.toggle_reqd(['customer', 'currency', 'price_list'], true);
                // No warehouse needed for service sale
            }

            // ============================================================
            // SUPPLIER LOGIC - For production, usluga_po_zakasu
            // ============================================================
            if (['Производство', 'Услуги по заказу'].includes(frm.doc.operation_type)) {
                frm.toggle_display('supplier', true);
                // Supplier is optional (not mandatory) - can be used for reference
                frm.toggle_reqd('supplier', false);
            }

            // ============================================================
            // MATERIAL TRANSFER LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'Перемещения') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], true);
            }

            // ============================================================
            // MATERIAL ISSUE LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'Списание материалов') {
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
                // No to_warehouse for Material Issue
            }

            // ============================================================
            // MATERIAL REQUEST LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'Запрос материалов') {
                frm.toggle_display('from_warehouse', true);
                frm.toggle_reqd('from_warehouse', true);
                // Ensure items table is visible
                frm.toggle_display('items', true);
            }

            // ============================================================
            // PURCHASE RECEIPT LOGIC
            // ============================================================
            if (frm.doc.operation_type === 'Приход на склад') {
                // Visibility
                frm.toggle_display(['supplier', 'from_warehouse', 'currency', 'items'], true);

                // Explicitly keep price_list hidden for purchase_receipt
                frm.toggle_display('price_list', false);

                // Dynamic labeling
                frm.set_df_property('from_warehouse', 'label', __('Принято на склад'));

                // Mandatory fields (explicitly via df_property as requested)
                frm.set_df_property('supplier', 'reqd', 1);
                frm.set_df_property('from_warehouse', 'reqd', 1);
            }

            // ============================================================
            // PRODUCTION HUB: Sales Order related operations
            // ============================================================
            if (['Производство', 'Расход по заказу', 'Услуги по заказу'].includes(frm.doc.operation_type)) {
                // All 3 need Sales Order link
                frm.toggle_display(['sales_order', 'sales_order_item'], true);
                frm.toggle_reqd('sales_order', true);
                // Show finished_good and production_qty
                frm.toggle_display(['finished_good', 'production_qty'], true);
            }

            // usluga_po_zakasu - Service costs only, NO warehouses needed
            if (frm.doc.operation_type === 'Услуги по заказу') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], false);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], false);
                frm.toggle_reqd(['finished_good', 'production_qty'], true);
            }

            // rasxod_po_zakasu - Material Transfer to WIP
            if (frm.doc.operation_type === 'Расход по заказу') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['from_warehouse', 'to_warehouse'], true);
                // Auto-default to WIP warehouse
                if (!frm.doc.to_warehouse && frm.doc.company) {
                    frm.trigger('set_wip_warehouse_default');
                }
            }

            // production - The Aggregator
            if (frm.doc.operation_type === 'Производство') {
                frm.toggle_display(['from_warehouse', 'to_warehouse'], true);
                frm.toggle_reqd(['finished_good', 'production_qty', 'from_warehouse', 'to_warehouse'], true);
                // Auto-set WIP warehouse as from_warehouse (source for consumption)
                if (!frm.doc.from_warehouse && frm.doc.company) {
                    frm.trigger('set_production_warehouses');
                }
            }
        }
    },
    set_production_warehouses(frm) {
        // Set default warehouses for production operation
        // from_warehouse = WIP (source), to_warehouse = Finished Goods (target)
        if (frm.doc.operation_type === 'Производство' && frm.doc.company) {
            // Set WIP as from_warehouse
            if (!frm.doc.from_warehouse) {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Warehouse',
                        filters: {
                            'company': frm.doc.company,
                            'warehouse_name': ['like', '%Work In Progress%'],
                            'is_group': 0
                        },
                        fields: ['name'],
                        limit_page_length: 1
                    },
                    async: false,
                    callback: function (r) {
                        if (r.message && r.message.length > 0) {
                            frm.set_value('from_warehouse', r.message[0].name);
                        } else {
                            // Try WIP naming
                            frappe.call({
                                method: 'frappe.client.get_list',
                                args: {
                                    doctype: 'Warehouse',
                                    filters: {
                                        'company': frm.doc.company,
                                        'warehouse_name': ['like', '%WIP%'],
                                        'is_group': 0
                                    },
                                    fields: ['name'],
                                    limit_page_length: 1
                                },
                                async: false,
                                callback: function (r2) {
                                    if (r2.message && r2.message.length > 0) {
                                        frm.set_value('from_warehouse', r2.message[0].name);
                                    }
                                }
                            });
                        }
                    }
                });
            }

            // Set Finished Goods as to_warehouse
            if (!frm.doc.to_warehouse) {
                frappe.call({
                    method: 'frappe.client.get_list',
                    args: {
                        doctype: 'Warehouse',
                        filters: {
                            'company': frm.doc.company,
                            'warehouse_name': ['like', '%Finished Goods%'],
                            'is_group': 0
                        },
                        fields: ['name'],
                        limit_page_length: 1
                    },
                    async: false,
                    callback: function (r) {
                        if (r.message && r.message.length > 0) {
                            frm.set_value('to_warehouse', r.message[0].name);
                        }
                    }
                });
            }
        }
    },
    set_wip_warehouse_default(frm) {
        // Set default WIP warehouse for rasxod_po_zakasu operation
        if (frm.doc.operation_type === 'Расход по заказу' && frm.doc.company && !frm.doc.to_warehouse) {
            // Search for WIP warehouse in the company using get_list for proper filtering
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Warehouse',
                    filters: {
                        'company': frm.doc.company,
                        'warehouse_name': ['like', '%Work In Progress%'],
                        'is_group': 0
                    },
                    fields: ['name'],
                    limit_page_length: 1
                },
                async: false,
                callback: function (r) {
                    if (r.message && r.message.length > 0) {
                        frm.set_value('to_warehouse', r.message[0].name);
                    } else {
                        // Try alternative WIP naming
                        frappe.call({
                            method: 'frappe.client.get_list',
                            args: {
                                doctype: 'Warehouse',
                                filters: {
                                    'company': frm.doc.company,
                                    'warehouse_name': ['like', '%WIP%'],
                                    'is_group': 0
                                },
                                fields: ['name'],
                                limit_page_length: 1
                            },
                            async: false,
                            callback: function (r2) {
                                if (r2.message && r2.message.length > 0) {
                                    frm.set_value('to_warehouse', r2.message[0].name);
                                }
                            }
                        });
                    }
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
        // Clear items table when sales_order changes in production mode
        if (frm.doc.operation_type === 'Производство') {
            frm.clear_table('items');
            frm.refresh_field('items');
        }
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

                        // ========================================
                        // PRODUCTION MODE: Auto-fetch materials and services
                        // ========================================
                        if (frm.doc.operation_type === 'Производство') {
                            frm.trigger('fetch_production_data');
                        }
                    }
                }
            });
        }
    },
    fetch_production_data(frm) {
        // Fetch WIP materials and service costs for Production Hub
        if (!frm.doc.sales_order || !frm.doc.sales_order_item) {
            // Silently return - will be called again when sales_order_item is selected
            return;
        }

        if (!frm.doc.from_warehouse) {
            // Silently return - will be called again when from_warehouse is set
            return;
        }

        frappe.call({
            method: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_production_data",
            args: {
                sales_order: frm.doc.sales_order,
                sales_order_item: frm.doc.sales_order_item,
                wip_warehouse: frm.doc.from_warehouse,
                finished_good: frm.doc.finished_good
            },
            freeze: true,
            freeze_message: __('Fetching production data...'),
            callback: function (r) {
                if (r.message) {
                    // Clear existing items table
                    frm.clear_table('items');

                    let materials = r.message.materials || [];
                    let services = r.message.services || [];

                    // Add WIP Materials (is_wip_item = 1)
                    materials.forEach(mat => {
                        frm.add_child('items', {
                            item_code: mat.item_code,
                            item_name: mat.item_name,
                            qty: mat.qty,
                            uom: mat.uom,
                            rate: mat.rate,
                            amount: mat.amount,
                            is_stock_item: mat.is_stock_item,
                            is_wip_item: 1  // Flag: This is a WIP material
                        });
                    });

                    // Add Service Items (is_wip_item = 0)
                    services.forEach(svc => {
                        frm.add_child('items', {
                            item_code: svc.item_code,
                            item_name: svc.item_name,
                            qty: svc.qty,
                            uom: svc.uom,
                            rate: svc.rate,
                            amount: svc.amount,
                            is_stock_item: svc.is_stock_item,
                            is_wip_item: 0  // Flag: This is a service (not from WIP)
                        });
                    });

                    frm.refresh_field('items');
                    frm.trigger('calculate_totals');

                    // User feedback
                    let msg = __('Loaded {0} materials and {1} services', [materials.length, services.length]);
                    if (materials.length === 0 && services.length === 0) {
                        frappe.msgprint({
                            title: __('No Data Found'),
                            message: __('No materials in WIP or services found for this Sales Order Item. Please create Rasxod/Usluga entries first.'),
                            indicator: 'orange'
                        });
                    } else {
                        frappe.show_alert({
                            message: msg,
                            indicator: 'green'
                        }, 5);
                    }
                }
            }
        });
    },
    price_list(frm) {
        // When price_list changes, re-fetch rates for all items
        if (frm.doc.price_list && frm.doc.currency) {
            (frm.doc.items || []).forEach(row => {
                if (row.item_code) {
                    fetch_and_set_rate(frm, row.doctype, row.name);
                }
            });
        }
    },
    currency(frm) {
        // When currency changes, re-fetch rates for all items
        if (frm.doc.price_list && frm.doc.currency) {
            (frm.doc.items || []).forEach(row => {
                if (row.item_code) {
                    fetch_and_set_rate(frm, row.doctype, row.name);
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

    from_warehouse: function (frm) {
        // From Warehouse o'zgarganda production mode uchun fetch qilish
        if (frm.doc.operation_type === 'Производство' && frm.doc.from_warehouse) {
            // Try to fetch production data if sales_order_item is already selected
            if (frm.doc.sales_order_item) {
                frm.trigger('fetch_production_data');
            }
        }
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
            // Fetch rate from Price List if price_list and currency are set
            if (frm.doc.price_list && frm.doc.currency) {
                fetch_and_set_rate(frm, cdt, cdn);
            }
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

function fetch_and_set_rate(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row.item_code || !frm.doc.price_list || !frm.doc.currency) return;

    frappe.call({
        method: 'premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_any_available_price',
        args: {
            item_code: row.item_code,
            preferred_price_list: frm.doc.price_list,
            currency: frm.doc.currency
        },
        callback: function (r) {
            if (!r.message) return;

            let rate = flt(r.message.rate);
            let source = r.message.source;

            frappe.model.set_value(cdt, cdn, 'rate', rate);
            calculate_row_amount(frm, cdt, cdn);
            frm.trigger('calculate_totals');

            if (rate && source && source !== frm.doc.price_list) {
                // Price found in a fallback list
                frappe.show_alert({
                    message: __("Narx '{0}' narxnomasidan olindi ({1})", [source, row.item_code]),
                    indicator: 'blue'
                }, 5);
            } else if (!rate) {
                frappe.show_alert({
                    message: __("Narx topilmadi: {0} uchun hech qaysi narx ro'yxatida narx yo'q", [row.item_code]),
                    indicator: 'orange'
                }, 5);
            }
        }
    });
}