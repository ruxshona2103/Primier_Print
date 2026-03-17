// Operation Type Mapping (Russian → Purpose)
// Запрос материалов → Material Request (Purchase)
// Приход на склад → Purchase Receipt
// Списание материалов → Stock Entry (Material Issue)
// Перемещения → Stock Entry (Material Transfer)
// Отгрузка товаров → Delivery Note (+ Inter-company)
// Расход по заказу → Material Transfer to WIP
// Услуги по заказу → Service cost logging
// Производство → Repack Stock Entry (Aggregator)

const PURCHASE_RECEIPT_OPERATION = "Приход на склад";

function normalize_operation_type(value) {
    return String(value || "")
        .trim()
        .replace(/A/g, "А")
        .replace(/a/g, "а");
}

function is_purchase_receipt_operation(value) {
    return normalize_operation_type(value) === PURCHASE_RECEIPT_OPERATION;
}

function should_use_valuation_rate(frm) {
    return normalize_operation_type(frm.doc.operation_type) === "Отгрузка товаров"
        && Boolean(frm.doc.target_company);
}

frappe.ui.form.on("Asosiy panel", {
    onload(frm) {
        frm._last_operation_type = normalize_operation_type(frm.doc.operation_type);
    },

    refresh(frm) {
        console.log("🔄 UI Refresh started for operation:", frm.doc.operation_type || "NOT SET");

        frm._last_operation_type = normalize_operation_type(frm.doc.operation_type);

        frm.trigger("setup_queries");
        frm.trigger("toggle_ui");
        frm.trigger("set_warehouse_filters");

        // Render custom buttons
        frm.trigger("render_custom_buttons");

        // Stock Ledger button - only shown for submitted documents
        if (frm.doc.docstatus === 1) {
            frm.add_custom_button(__('Stock Ledger'), function () {
                frappe.route_options = {
                    voucher_no: frm.doc.name,
                    from_date: frm.doc.posting_date,
                    to_date: frm.doc.posting_date,
                    company: frm.doc.company
                };
                frappe.set_route("query-report", "Stock Ledger");
            }, __("View"));
        }
    },

    render_custom_buttons(frm) {
        // Remove existing Purchase Order button to prevent duplicates
        if (frm.custom_buttons && frm.custom_buttons["Get Items From"]) {
            frm.remove_custom_button("Purchase Order", "Get Items From");
        }

        // Robust string comparison with trim and type coercion
        let operation_type = normalize_operation_type(frm.doc.operation_type);
        let is_purchase_receipt = is_purchase_receipt_operation(operation_type);
        let is_draft = frm.doc.docstatus === 0;

        console.log("🔍 DEBUG - Operation Type:", operation_type);
        console.log("🔍 DEBUG - Is Purchase Receipt:", is_purchase_receipt);
        console.log("🔍 DEBUG - Is Draft:", is_draft);

        // "Get Items From" button for Purchase Receipt operation
        if (is_purchase_receipt && is_draft) {
            frm.add_custom_button(__('Purchase Order'), function () {
                console.log("🔘 BUTTON CLICKED - Starting Purchase Order dialog");

                // Validation: Ensure Supplier and Company are selected
                if (!frm.doc.supplier || !frm.doc.company) {
                    frappe.msgprint({
                        title: __('Ma\'lumot etishmayapti'),
                        message: __('Iltimos, avval Kompaniya va Ta\'minotchini tanlang!'),
                        indicator: 'red'
                    });
                    return;
                }

                console.log("✅ Opening standard MultiSelectDialog");
                console.log("📋 Filters:", { supplier: frm.doc.supplier, company: frm.doc.company });

                // Standard Frappe MultiSelectDialog - No custom query needed
                let d = new frappe.ui.form.MultiSelectDialog({
                    doctype: "Purchase Order",
                    target: frm,
                    setters: {
                        supplier: frm.doc.supplier || undefined,
                        company: frm.doc.company || undefined
                    },
                    add_filters_group: 1,
                    date_field: "transaction_date",
                    get_query() {
                        return {
                            filters: {
                                docstatus: 1,
                                supplier: frm.doc.supplier,
                                company: frm.doc.company,
                                status: ["not in", ["Completed", "Closed", "Cancelled"]]
                            }
                        };
                    },
                    primary_action_label: __("Tanlash va Yuklash"),
                    action(selections) {
                        d.dialog.hide();
                        console.log("✅ Selections:", selections);

                        if (selections && selections.length > 0) {
                            // STEP 1: Fetch currency metadata from the first PO BEFORE loading items
                            // This prevents the '$' symbol race condition
                            let first_po = selections[0];
                            frappe.call({
                                method: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_purchase_order_meta",
                                args: { po_name: first_po },
                                freeze: true,
                                freeze_message: __("Valyuta ma'lumoti yuklanmoqda..."),
                                callback: function (meta_r) {
                                    // Apply currency FIRST so all subsequent formatting uses correct symbol
                                    if (meta_r.message) {
                                        let meta = meta_r.message;
                                        if (meta.currency) {
                                            frm.set_value('currency', meta.currency);
                                            frm.refresh_field('currency');
                                        }
                                        if (meta.conversion_rate) {
                                            frm.set_value('exchange_rate', flt(meta.conversion_rate));
                                            frm.refresh_field('exchange_rate');
                                        }
                                        if (meta.buying_price_list) {
                                            frm.set_value('price_list', meta.buying_price_list);
                                        }
                                    }

                                    // STEP 2: Now fetch items (currency is already set)
                                    frappe.call({
                                        method: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_items_from_purchase_orders",
                                        args: {
                                            source_names: JSON.stringify(selections)
                                        },
                                        freeze: true,
                                        freeze_message: __("Tovarlar yuklanmoqda..."),
                                        callback: function (r) {
                                            console.log("📦 Items received:", r.message);

                                            if (r.message && r.message.length > 0) {
                                                frm.clear_table("items");
                                                r.message.forEach(item => {
                                                    console.log("📦 Mapping remaining qty for PO:", item.purchase_order, "| Item:", item.item_code, "| Remaining Qty:", item.qty);
                                                    let row = frm.add_child("items");
                                                    Object.assign(row, item);
                                                });
                                                frm.refresh_field("items");
                                                frm.trigger("calculate_totals");

                                                let currency_label = frm.doc.currency || '';
                                                frappe.show_alert({
                                                    message: __("{0} ta tovar muvaffaqiyatli yuklandi ({1})", [r.message.length, currency_label]),
                                                    indicator: "green"
                                                }, 5);

                                                if (meta_r.message && meta_r.message.currency) {
                                                    frappe.show_alert({
                                                        message: __('Valyuta PO dan sinxronlandi: {0}', [meta_r.message.currency]),
                                                        indicator: 'blue'
                                                    }, 3);
                                                }
                                            } else {
                                                frappe.msgprint({
                                                    title: __('Ma\'lumot yo\'q'),
                                                    message: __('Serverdan bo\'sh ro\'yxat keldi. Purchase Order statusini tekshiring. Selections: ') + JSON.stringify(selections),
                                                    indicator: 'orange'
                                                });
                                            }
                                        },
                                        error: function (r) {
                                            console.error("❌ Error:", r);
                                            frappe.msgprint({
                                                title: __('Xatolik'),
                                                message: __('Tovarlarni yuklashda xatolik yuz berdi.'),
                                                indicator: 'red'
                                            });
                                        }
                                    });
                                }
                            });
                        }
                    }
                });
            }, __("Get Items From"));

            console.log("✅ Purchase Order button added");
        }
    },

    company(frm) {
        frm.trigger("setup_queries");
        frm.set_value('sales_order', '');
        frm.set_value('sales_order_item', '');
        frm.set_value('finished_good', '');
        // Clear warehouses when company changes and reset defaults
        frm.set_value('from_warehouse', '');
        frm.set_value('to_warehouse', '');
        frm.trigger('set_warehouse_filters');
        // Re-apply warehouse defaults based on operation type
        if (frm.doc.operation_type === 'Расход по заказу') {
            frm.trigger('set_wip_warehouse_default');
        } else if (frm.doc.operation_type === 'Производство') {
            frm.trigger('set_production_warehouses');
        }
    },
    operation_type(frm) {
        const current_operation_type = normalize_operation_type(frm.doc.operation_type);
        const previous_operation_type = normalize_operation_type(frm._last_operation_type);
        const is_manual_change = Boolean(previous_operation_type)
            && current_operation_type !== previous_operation_type
            && frm.is_dirty();

        if (is_manual_change) {
            frm.trigger("clear_operation_fields");
        }

        frm._last_operation_type = current_operation_type;
        frm.trigger("toggle_ui");
        frm.trigger("render_custom_buttons");
    },

    before_save(frm) {
        console.log("Supplier value before save:", frm.doc.supplier);
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
                
                // Fetch rates based on the new conditions
                if (should_use_valuation_rate(frm)) {
                    refetch_item_rates(frm);
                }
                
                frm.trigger("toggle_ui");
                frm.trigger("setup_queries");
            });
        } else {
            // Customer cleared - reset price_list and allow manual selection
            frm.set_value("target_company", "");
            frm.set_df_property("price_list", "read_only", 0);
            
            if (frm.doc.operation_type === 'Отгрузка товаров') {
                 refetch_item_rates(frm);
            }
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
    target_company(frm) {
        // Target Company o'zgarsa, To Warehouse fieldini tozalaymiz va filtrni yangilaymiz
        frm.set_value('to_warehouse', '');
        frm.trigger('set_warehouse_filters');
    },
    from_warehouse(frm) {
        // From Warehouse o'zgarganda production mode uchun fetch qilish
        if (frm.doc.operation_type === 'Производство' && frm.doc.from_warehouse) {
            if (frm.doc.sales_order_item) {
                frm.trigger('fetch_production_data');
            }
        }
        
        if (should_use_valuation_rate(frm)) {
            refetch_item_rates(frm);
        }
    },
    set_warehouse_filters(frm) {
        // "From Warehouse" filtrini o'rnatish (Asosiy Company bo'yicha)
        frm.set_query('from_warehouse', function () {
            return {
                filters: {
                    'company': frm.doc.company,
                    'is_group': 0
                }
            };
        });
        // "To Warehouse" filtrini o'rnatish (Target Company bo'yicha)
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
    },
    toggle_ui(frm) {
        console.log("🎨 UI Toggle started for:", frm.doc.operation_type || "EMPTY");

        // ========================================
        // CRITICAL: ALWAYS show basic fields
        // ========================================
        if (frm.fields_dict['operation_type']) {
            frm.toggle_display('operation_type', true);
            frm.toggle_reqd('operation_type', true);
        }
        if (frm.fields_dict['company']) {
            frm.toggle_display('company', true);
            frm.toggle_reqd('company', true);
        }
        if (frm.fields_dict['posting_date']) {
            frm.toggle_display('posting_date', true);
            frm.toggle_reqd('posting_date', true);
        }

        // Default hide and un-require all optional fields
        // NOTE: exchange_rate is hidden by default — only shown for financial operations
        const fields_to_toggle = [
            'customer', 'currency', 'exchange_rate', 'price_list', 'supplier',
            'from_warehouse', 'to_warehouse', 'target_warehouse', 'target_company',
            'finished_good', 'production_qty',
            'sales_order', 'sales_order_item'
        ];

        // Safely toggle only fields that exist
        fields_to_toggle.forEach(field => {
            if (frm.fields_dict[field]) {
                frm.toggle_display(field, false);
                frm.toggle_reqd(field, false);
            }
        });

        // Reset label back to default for non-purchase_receipt
        if (frm.fields_dict['from_warehouse']) {
            frm.set_df_property('from_warehouse', 'label', __('From Warehouse'));
        }

        // Reset mandatory flags (explicitly via df_property as requested)
        if (frm.fields_dict['supplier']) {
            frm.set_df_property('supplier', 'reqd', 0);
        }
        if (frm.fields_dict['from_warehouse']) {
            frm.set_df_property('from_warehouse', 'reqd', 0);
        }

        // ========================================
        // SAFETY: If no operation_type, show items table at least
        // ========================================
        if (!frm.doc.operation_type) {
            console.log("⚠️ No operation_type set - showing basic fields only");
            if (frm.fields_dict['items']) {
                frm.toggle_display('items', true);
            }
            return; // Exit early to prevent hiding everything
        }

        if (frm.doc.operation_type) {
            // ============================================================
            // DELIVERY NOTE LOGIC - Full Inter-Company Support
            // ============================================================
            if (frm.doc.operation_type === 'Отгрузка товаров') {
                // Dynamic Visibility: Show all relevant fields for inter-company transfer
                frm.toggle_display(['customer', 'target_company', 'from_warehouse', 'target_warehouse', 'currency', 'exchange_rate', 'price_list', 'payment_due_date', 'items', 'total_quantity', 'total_amount'], true);
                frm.toggle_reqd(['customer', 'currency', 'price_list', 'from_warehouse'], true);

                // For internal customers, make target_company visible
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
            // SUPPLIER LOGIC - only for service cost operation
            // ============================================================
            if (frm.doc.operation_type === 'Услуги по заказу') {
                frm.toggle_display('supplier', true);
            }

            // Supplier is MANDATORY for service operations (Purchase Invoice creation)
            if (frm.doc.operation_type === 'Услуги по заказу') {
                frm.toggle_reqd('supplier', true);
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
            if (is_purchase_receipt_operation(frm.doc.operation_type)) {
                // Visibility — show currency AND exchange_rate for proper multi-currency support
                frm.toggle_display(['supplier', 'from_warehouse', 'currency', 'exchange_rate', 'items'], true);

                // Explicitly keep price_list hidden for purchase_receipt
                frm.toggle_display('price_list', false);

                // Dynamic labeling
                frm.set_df_property('from_warehouse', 'label', __('Принято на склад'));

                // Mandatory fields (explicitly via df_property as requested)
                frm.set_df_property('supplier', 'reqd', 1);
                frm.set_df_property('from_warehouse', 'reqd', 1);

                // Set default currency to company's base currency if not already set
                if (!frm.doc.currency && frm.doc.company) {
                    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                        if (r && r.default_currency) {
                            frm.set_value('currency', r.default_currency);
                        }
                    });
                }
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

                // Multi-Currency Support for Service Costs
                frm.toggle_display(['currency', 'exchange_rate'], true);
                frm.toggle_reqd('currency', true);

                // Set default currency to company's base currency if not set
                if (!frm.doc.currency && frm.doc.company) {
                    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                        if (r && r.default_currency) {
                            frm.set_value('currency', r.default_currency);
                        }
                    });
                }
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
                frm.toggle_display(['from_warehouse', 'to_warehouse', 'currency', 'exchange_rate'], true);
                frm.toggle_reqd(['finished_good', 'production_qty', 'from_warehouse', 'to_warehouse'], true);
                // Auto-set WIP warehouse as from_warehouse (source for consumption)
                if (!frm.doc.from_warehouse && frm.doc.company) {
                    frm.trigger('set_production_warehouses');
                }

                // Default currency if not set
                if (!frm.doc.currency && frm.doc.company) {
                    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                        if (r && r.default_currency) {
                            frm.set_value('currency', r.default_currency);
                        }
                    });
                }
            }
        }

        // ============================================================
        // CENTRALIZED: Exchange Rate read-only logic
        // If currency == company's base currency → exchange_rate = 1, read-only
        // If currency != company's base currency → exchange_rate editable
        // ============================================================
        frm.trigger('sync_exchange_rate_state');
    },
    sync_exchange_rate_state(frm) {
        if (!frm.doc.currency || !frm.doc.company) return;

        frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
            if (!r || !r.default_currency) return;

            if (frm.doc.currency === r.default_currency) {
                // Same currency → force 1.0 and lock
                if (flt(frm.doc.exchange_rate) !== 1.0) {
                    frm.set_value('exchange_rate', 1.0);
                }
                frm.set_df_property('exchange_rate', 'read_only', 1);
            } else {
                // Foreign currency → allow editing
                frm.set_df_property('exchange_rate', 'read_only', 0);
            }
        });
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
                filters: {
                    company: frm.doc.company || '',
                    docstatus: 1
                }
            };
        });

        // Sales Order Item query - Use custom function to bypass permissions
        frm.set_query("sales_order_item", function () {
            if (!frm.doc.company || !frm.doc.sales_order) {
                frappe.show_alert({
                    message: __('Please select Company and Sales Order first'),
                    indicator: 'orange'
                });
                return { filters: { name: ['=', ''] } };
            }
            return {
                query: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_so_items",
                filters: {
                    company: frm.doc.company,
                    sales_order: frm.doc.sales_order
                }
            };
        });
    },
    sales_order(frm) {
        // Clear sales_order_item and finished_good when sales_order changes (like Stock Entry)
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
        // Fetch WIP materials and service costs for Production Hub using advanced aggregator
        if (!frm.doc.sales_order_item) {
            // Silently return - will be called again when sales_order_item is selected
            return;
        }

        if (!frm.doc.from_warehouse) {
            // Silently return - will be called again when from_warehouse is set
            return;
        }

        frappe.call({
            method: "premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_all_costs_for_production",
            args: {
                sales_order_item: frm.doc.sales_order_item,
                wip_warehouse: frm.doc.from_warehouse,
                company: frm.doc.company
            },
            freeze: true,
            freeze_message: __('Fetching materials and service costs...'),
            callback: function (r) {
                if (r.message && r.message.has_data) {
                    // Clear existing items table
                    frm.clear_table('items');

                    let materials = r.message.materials || [];
                    let services = r.message.services || [];
                    let purchase_invoices = r.message.purchase_invoices || [];

                    console.log('📦 Production Data Loaded:', {
                        materials_count: materials.length,
                        services_count: services.length,
                        total_material_cost: r.message.total_material_cost,
                        total_service_cost: r.message.total_service_cost,
                        purchase_invoices: purchase_invoices
                    });

                    // Add WIP Materials (is_wip_material = 1)
                    materials.forEach(mat => {
                        let row = frm.add_child('items', {
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

                    // Add Service Items (is_wip_material = 0) with visual hint
                    services.forEach(svc => {
                        let row = frm.add_child('items', {
                            item_code: svc.item_code,
                            item_name: svc.item_name,
                            qty: svc.qty,
                            uom: svc.uom,
                            rate: svc.rate,
                            amount: svc.amount,
                            is_stock_item: 0,
                            is_wip_item: 0  // Flag: This is a service cost
                        });

                        // Visual hint: Service costs shown with description
                        if (svc.description) {
                            frappe.model.set_value(row.doctype, row.name, 'item_name',
                                '🔧 ' + svc.item_name + ' (Service)');
                        }
                    });

                    frm.refresh_field('items');
                    frm.trigger('calculate_totals');

                    // User feedback with detailed summary
                    let msg_parts = [];
                    if (materials.length > 0) {
                        msg_parts.push(__('Materials: {0} items ({1})', [
                            materials.length,
                            frappe.format(r.message.total_material_cost, { fieldtype: 'Currency', currency: r.message.company_currency })
                        ]));
                    }
                    if (services.length > 0) {
                        msg_parts.push(__('Services: {0} items ({1})', [
                            services.length,
                            frappe.format(r.message.total_service_cost, { fieldtype: 'Currency', currency: r.message.company_currency })
                        ]));
                    }
                    if (purchase_invoices.length > 0) {
                        msg_parts.push(__('Purchase Invoices: {0}', [purchase_invoices.join(', ')]));
                    }

                    frappe.show_alert({
                        message: msg_parts.join('<br>'),
                        indicator: 'green'
                    }, 5);

                } else {
                    // No data found
                    frm.clear_table('items');
                    frm.refresh_field('items');

                    frappe.msgprint({
                        title: __('No Data Found'),
                        message: __('No materials in WIP or service costs found for Sales Order Item: {0}.<br><br>' +
                            'Please ensure:<br>' +
                            '1. "Расход по заказу" (Material Transfer to WIP) entries exist<br>' +
                            '2. "Услуги по заказу" (Service Cost) Purchase Invoices are submitted',
                            [frm.doc.sales_order_item || 'Not Selected']),
                        indicator: 'orange'
                    });
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
        // Auto-fetch exchange rate when currency changes
        if (frm.doc.currency && frm.doc.company) {
            // Get company's base currency
            frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                if (r && r.default_currency) {
                    let company_currency = r.default_currency;

                    // If transaction currency is same as company currency, exchange rate = 1
                    if (frm.doc.currency === company_currency) {
                        frm.set_value('exchange_rate', 1.0);
                    } else {
                        // Fetch current exchange rate from ERPNext
                        frappe.call({
                            method: 'erpnext.setup.utils.get_exchange_rate',
                            args: {
                                from_currency: frm.doc.currency,
                                to_currency: company_currency,
                                transaction_date: frm.doc.posting_date || frappe.datetime.get_today()
                            },
                            callback: function (r) {
                                if (r.message) {
                                    frm.set_value('exchange_rate', flt(r.message));
                                    frappe.show_alert({
                                        message: __('Kurs yangilandi: {0}', [flt(r.message, 6)]),
                                        indicator: 'green'
                                    }, 3);
                                }
                            }
                        });
                    }
                }
            });
        }

        // When currency changes, re-fetch rates for all items (for operations with price_list)
        if (frm.doc.price_list && frm.doc.currency) {
            (frm.doc.items || []).forEach(row => {
                if (row.item_code) {
                    fetch_and_set_rate(frm, row.doctype, row.name);
                }
            });
        }

        // Update exchange_rate read-only state based on new currency
        frm.trigger('sync_exchange_rate_state');
    },

    exchange_rate(frm) {
        // Recalculate totals when exchange rate changes (for display purposes)
        frm.trigger('calculate_totals');
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

        // For multi-currency operations, show base amount info
        // Applies to both 'Услуги по заказу' and 'Приход на склад'
        let doc_currency = frm.doc.currency || '';
        let needs_base_display = ['Услуги по заказу', 'Приход на склад'].includes(frm.doc.operation_type);

        if (needs_base_display && doc_currency && frm.doc.exchange_rate && frm.doc.company) {
            frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
                if (r && r.default_currency && doc_currency !== r.default_currency) {
                    let base_total = total_amount * flt(frm.doc.exchange_rate);
                    frm.set_df_property('total_amount', 'description',
                        __('Bazaviy summa: {0}', [
                            frappe.format(base_total, { fieldtype: 'Currency', currency: r.default_currency })
                        ])
                    );
                } else {
                    frm.set_df_property('total_amount', 'description', '');
                }
            });
        } else {
            frm.set_df_property('total_amount', 'description', '');
        }
    }
});

// NOTE: All 'Asosiy panel' handlers are in the SINGLE block above.
// Do NOT add a second frappe.ui.form.on('Asosiy panel', {...}) here —
// it would override the refresh/company/etc. handlers above and break the UI.

// Child Table: Asosiy panel item
frappe.ui.form.on('Asosiy panel item', {
    item_code: function (frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code) {
            fetch_and_set_rate(frm, cdt, cdn);
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

function refetch_item_rates(frm) {
    if (frm.doc.items) {
        frm.doc.items.forEach(row => {
            if (row.item_code) {
                fetch_and_set_rate(frm, row.doctype, row.name);
            }
        });
    }
}

function fetch_and_set_rate(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    if (!row.item_code) return;

    if (should_use_valuation_rate(frm)) {
        if (!frm.doc.company || !frm.doc.from_warehouse) return;

        frappe.call({
            method: 'premierprint.premierprint.doctype.asosiy_panel.asosiy_panel.get_item_valuation_rate',
            args: {
                item_code: row.item_code,
                warehouse: frm.doc.from_warehouse,
                posting_date: frm.doc.posting_date,
                posting_time: frm.doc.posting_time
            },
            callback: function (r) {
                if (r.message !== undefined && r.message !== null) {
                    let rate = flt(r.message);
                    frappe.model.set_value(cdt, cdn, 'rate', rate);
                    calculate_row_amount(frm, cdt, cdn);
                    frm.trigger('calculate_totals');
                    
                    // Make rate read-only for exact stock valuation
                    let grid_row = frm.fields_dict.items.grid.get_row(cdn);
                    if (grid_row) {
                        grid_row.toggle_editable('rate', false);
                    }
                }
            }
        });

        return;
    }

    if (!frm.doc.price_list || !frm.doc.currency) return;

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