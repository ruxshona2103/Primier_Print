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

            // ISSUE 6: Supplier ONLY for purchase_request and usluga_po_zakasu
            if (['purchase_request', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
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

            // ISSUE 1, 2, 4, 5: Sales Order fields for production, rasxod_po_zakasu, usluga_po_zakasu
            if (['production', 'rasxod_po_zakasu', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                frm.toggle_display(['sales_order', 'sales_order_item'], true);
                frm.toggle_reqd('sales_order', true);
            }

            // ISSUE 4 & 5: Production-specific fields
            if (['production', 'usluga_po_zakasu'].includes(frm.doc.operation_type)) {
                frm.toggle_display(['finished_good', 'production_qty', 'to_warehouse'], true);
                frm.toggle_reqd(['finished_good', 'production_qty', 'from_warehouse', 'to_warehouse'], true);
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

        // Sales Order Item query - FILTER by selected Sales Order (like Stock Entry)
        frm.set_query("sales_order_item", function () {
            let so = frm.doc.sales_order;
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
    sales_order(frm) {
        // Clear sales_order_item and finished_good when sales_order changes (like Stock Entry)
        if (!frm.doc.sales_order) {
            frm.set_value("sales_order_item", "");
        }
        frm.set_value("sales_order_item", "");
        frm.set_value("finished_good", "");
    },
    sales_order_item(frm) {
        // Auto-fetch item_code and qty from Sales Order Item
        if (frm.doc.sales_order_item) {
            frappe.db.get_value("Sales Order Item", frm.doc.sales_order_item, ["item_code", "qty"], (r) => {
                if (r) {
                    if (r.item_code) {
                        frm.set_value("finished_good", r.item_code);
                    }
                    if (r.qty && !frm.doc.production_qty) {
                        frm.set_value("production_qty", r.qty);
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

frappe.ui.form.on("Asosiy panel item", {
    item_code(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.item_code) {
            frappe.db.get_value("Item", row.item_code, ["item_name", "stock_uom", "valuation_rate", "standard_rate", "is_stock_item"], (r) => {
                if (r) {
                    frappe.model.set_value(cdt, cdn, "item_name", r.item_name);
                    frappe.model.set_value(cdt, cdn, "uom", r.stock_uom);
                    frappe.model.set_value(cdt, cdn, "is_stock_item", r.is_stock_item);
                    let rate = r.valuation_rate || r.standard_rate || 0;
                    frappe.model.set_value(cdt, cdn, "rate", rate);
                }
            });
        }
    },
    qty(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, "amount", row.qty * row.rate);
        frm.events.calculate_totals(frm);
    },
    rate(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        frappe.model.set_value(cdt, cdn, "amount", row.qty * row.rate);
        frm.events.calculate_totals(frm);
    },
    items_remove(frm) {
        frm.events.calculate_totals(frm);
    }
});