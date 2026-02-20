// Copyright (c) 2025, abdulloh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kassa", {

    refresh: function(frm) {
        // NEW: Register kassa query immediately on refresh so it is always active.
        frm.trigger("register_kassa_query");

        frm.set_query("expense_account", function() {
            return {
                filters: {
                    company: frm.doc.company,
                    root_type: "Expense",
                    is_group: 0
                }
            };
        });

        frm.trigger("set_mode_of_payment_query");

        if (frm.doc.mode_of_payment && frm.doc.company) {
            frm.trigger("update_balance");
        }
        if (frm.doc.mode_of_payment_to && frm.doc.company) {
            frm.trigger("update_balance_to");
        }

        frm.trigger("set_mode_of_payment_to_query");

        if (frm.doc.transaction_type === "Конвертация" && !frm.doc.exchange_rate) {
            frm.trigger("fetch_exchange_rate");
        }

        frm.trigger("update_balance_label");

        // NEW: Apply disabled-field guard on refresh (handles page reload on existing docs)
        frm.trigger("apply_kassa_field_state");
    },

    // ─── NEW: Dedicated trigger to register the server-side query ────────────
    // Isolating this into its own trigger means it can be called from multiple
    // places (refresh, company change, transaction_type callback) without
    // duplicating the query registration logic.
    register_kassa_query: function(frm) {
        frm.set_query("kassa", function() {
            return {
                // Routes to the @whitelist Python function — actual filtering
                // enforced server-side. The company filter here is a UX hint only.
                query: "premierprint.premierprint.doctype.kassa.kassa.get_kassa_accounts",
                filters: {
                    company: frm.doc.company || ""
                }
            };
        });
    },

    // ─── NEW: Apply disabled/enabled state to kassa field ────────────────────
    // When company is absent: kassa field is read_only + cleared (fail-safe default)
    // When company is present: kassa field is editable
    apply_kassa_field_state: function(frm) {
        const has_company = !!(frm.doc.company);
        frm.set_df_property("kassa", "read_only", has_company ? 0 : 1);

        // Show a subtle placeholder hint when disabled
        if (!has_company) {
            frm.set_df_property("kassa", "description",
                __("Сначала выберите компанию"));
        } else {
            frm.set_df_property("kassa", "description", "");
        }
        frm.refresh_field("kassa");
    },

    company: function(frm) {
        // FIX: Clear kassa on company change to prevent orphaned cross-company
        // account references. This is the primary data integrity guard.
        frm.set_value("kassa", "");
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account", "");
        frm.set_value("balance", 0);
        frm.set_value("party", "");
        frm.set_value("expense_account", "");

        // FIX: Re-register query and update field state AFTER company is set.
        // Calling register_kassa_query here ensures the query closure captures
        // the new company value, not a stale one from before the change.
        frm.trigger("register_kassa_query");
        frm.trigger("apply_kassa_field_state");
    },

    mode_of_payment: function(frm) {
        if (frm.doc.mode_of_payment && frm.doc.company) {
            frappe.call({
                method: "premierprint.premierprint.doctype.kassa.kassa.get_cash_account_with_currency",
                args: {
                    mode_of_payment: frm.doc.mode_of_payment,
                    company: frm.doc.company
                },
                callback: function(r) {
                    if (r.message && r.message.account) {
                        frm.set_value("cash_account", r.message.account);
                        frm.set_value("cash_account_currency", r.message.currency);
                        frm.trigger("update_balance");
                        frm.trigger("validate_currency");
                    } else {
                        frappe.msgprint(__("Для данного способа оплаты не настроен счет кассы для компании {0}",
                            [frm.doc.company]));
                        frm.set_value("cash_account", "");
                        frm.set_value("cash_account_currency", "");
                        frm.set_value("balance", 0);
                    }
                }
            });
        } else {
            frm.set_value("cash_account", "");
            frm.set_value("cash_account_currency", "");
            frm.set_value("balance", 0);
        }

        if (in_list(["Перемещения", "Конвертация"], frm.doc.transaction_type)) {
            frm.set_value("mode_of_payment_to", "");
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
            frm.trigger("set_mode_of_payment_to_query");
        }
    },

    update_balance: function(frm) {
        if (frm.doc.cash_account && frm.doc.company) {
            frappe.call({
                method: "premierprint.premierprint.doctype.kassa.kassa.get_account_balance",
                args: { account: frm.doc.cash_account, company: frm.doc.company },
                callback: function(r) { frm.set_value("balance", r.message || 0); }
            });
        }
    },

    transaction_type: function(frm) {
        frm.set_value("party_type", "");
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
        frm.set_value("party_name", "");
        frm.set_value("expense_account_name", "");
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account", "");
        frm.set_value("balance", 0);
        frm.set_value("mode_of_payment_to", "");
        frm.set_value("cash_account_to", "");
        frm.set_value("balance_to", 0);
        frm.set_value("exchange_rate", 0);
        frm.set_value("debit_amount", 0);
        frm.set_value("credit_amount", 0);

        frm.trigger("set_mode_of_payment_query");
        frm.trigger("set_mode_of_payment_to_query");

        if (frm.doc.transaction_type === "Перемещения" && !frm.doc.company) {
            // FIX: Re-register kassa query INSIDE the callback, after company resolves.
            // Previously set_query was called synchronously before this async call
            // completed, meaning frm.doc.company was still null when the closure captured it.
            frappe.call({
                method: "frappe.client.get_value",
                args: { doctype: "Global Defaults", fieldname: "default_company" },
                callback: function(r) {
                    if (r.message && r.message.default_company) {
                        frm.set_value("company", r.message.default_company);
                        // FIX: Now company is set — re-register query with correct value
                        frm.trigger("register_kassa_query");
                        frm.trigger("apply_kassa_field_state");
                    }
                }
            });
        } else {
            // Company already set — update query and state synchronously
            frm.trigger("register_kassa_query");
            frm.trigger("apply_kassa_field_state");
        }

        if (frm.doc.transaction_type === "Конвертация") {
            frm.trigger("fetch_exchange_rate");
        }

        frm.trigger("update_balance_label");
    },

    mode_of_payment_to: function(frm) {
        if (frm.doc.mode_of_payment_to && frm.doc.company) {
            frappe.call({
                method: "premierprint.premierprint.doctype.kassa.kassa.get_cash_account",
                args: { mode_of_payment: frm.doc.mode_of_payment_to, company: frm.doc.company },
                callback: function(r) {
                    if (r.message) {
                        frm.set_value("cash_account_to", r.message);
                        frm.trigger("update_balance_to");
                    } else {
                        frappe.msgprint(__("Для данного способа оплаты не настроен счет кассы для компании {0}",
                            [frm.doc.company]));
                        frm.set_value("cash_account_to", "");
                        frm.set_value("balance_to", 0);
                    }
                }
            });
        } else {
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
        }
    },

    update_balance_to: function(frm) {
        if (frm.doc.cash_account_to && frm.doc.company) {
            frappe.call({
                method: "premierprint.premierprint.doctype.kassa.kassa.get_account_balance",
                args: { account: frm.doc.cash_account_to, company: frm.doc.company },
                callback: function(r) { frm.set_value("balance_to", r.message || 0); }
            });
        }
    },

    set_mode_of_payment_query: function(frm) {
        frm.set_query("mode_of_payment", function() {
            let filters = {};
            if (frm.doc.transaction_type === "Перемещения") {
                filters.name = ["in", ["Cash UZS", "Bank (No ref)"]];
            }
            return { filters: filters };
        });
    },

    set_mode_of_payment_to_query: function(frm) {
        frm.set_query("mode_of_payment_to", function() {
            let filters = {};
            if (frm.doc.transaction_type === "Перемещения") {
                if (frm.doc.mode_of_payment === "Cash UZS") filters.name = "Bank (No ref)";
                else if (frm.doc.mode_of_payment === "Bank (No ref)") filters.name = "Cash UZS";
            } else if (frm.doc.transaction_type === "Конвертация") {
                if (frm.doc.mode_of_payment === "Cash USD") {
                    filters.name = ["in", ["Cash UZS", "Bank (No ref)"]];
                } else if (in_list(["Cash UZS", "Bank (No ref)"], frm.doc.mode_of_payment)) {
                    filters.name = "Cash USD";
                }
            }
            return { filters: filters };
        });
    },

    fetch_exchange_rate: function(frm) {
        frappe.call({
            method: "premierprint.premierprint.doctype.kassa.kassa.get_exchange_rate",
            args: {
                from_currency: "USD",
                to_currency: "UZS",
                date: frm.doc.date || frappe.datetime.get_today()
            },
            callback: function(r) {
                if (r.message) frm.set_value("exchange_rate", r.message);
            }
        });
    },

    debit_amount: function(frm) { frm.trigger("calculate_conversion_amount"); },
    exchange_rate: function(frm) { frm.trigger("calculate_conversion_amount"); },

    calculate_conversion_amount: function(frm) {
        if (frm.doc.transaction_type !== "Конвертация") return;
        if (!frm.doc.debit_amount || !frm.doc.exchange_rate) return;

        if (in_list(["Cash UZS", "Bank (No ref)"], frm.doc.mode_of_payment)) {
            frm.set_value("credit_amount", flt(flt(frm.doc.debit_amount) / flt(frm.doc.exchange_rate), 2));
        } else if (frm.doc.mode_of_payment === "Cash USD") {
            frm.set_value("credit_amount", flt(flt(frm.doc.debit_amount) * flt(frm.doc.exchange_rate), 0));
        }
    },

    update_balance_label: function(frm) {
        const label = in_list(["Перемещения", "Конвертация"], frm.doc.transaction_type)
            ? "Остаток (откуда)" : "Остаток";
        frm.set_df_property("balance", "label", label);
        frm.refresh_field("balance");
    },

    party_type: function(frm) {
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
        frm.set_value("party_name", "");
        frm.set_value("expense_account_name", "");

        if (frm.doc.party_type === "Расходы") {
            frm.set_df_property("expense_account", "reqd", 1);
            frm.set_df_property("party", "reqd", 0);
        } else if (frm.doc.party_type === "Дивиденд") {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 0);
        } else if (frm.doc.party_type) {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 1);
        } else {
            frm.set_df_property("expense_account", "reqd", 0);
            frm.set_df_property("party", "reqd", 0);
        }
        frm.refresh_fields();
    },

    party: function(frm) {
        if (frm.doc.party && frm.doc.party_type) {
            const name_field = get_party_name_field(frm.doc.party_type);
            if (name_field) {
                frappe.db.get_value(frm.doc.party_type, frm.doc.party, name_field, function(r) {
                    if (r && r[name_field]) frm.set_value("party_name", r[name_field]);
                });
            }
            if (in_list(["Customer", "Supplier"], frm.doc.party_type)) {
                frappe.call({
                    method: "premierprint.premierprint.doctype.kassa.kassa.get_party_currency",
                    args: { party_type: frm.doc.party_type, party: frm.doc.party, company: frm.doc.company },
                    callback: function(r) {
                        if (r.message) {
                            frm.set_value("party_currency", r.message);
                            frm.trigger("validate_currency");
                        }
                    }
                });
            }
        } else {
            frm.set_value("party_name", "");
            frm.set_value("party_currency", "");
        }
    },

    validate_currency: function(frm) {
        if (frm.doc.cash_account_currency && frm.doc.party_currency) {
            if (frm.doc.cash_account_currency !== frm.doc.party_currency) {
                frappe.validated = false;
                frappe.msgprint({
                    title: __("Ошибка валюты"),
                    indicator: "red",
                    message: __("Валюта кассы ({0}) не совпадает с валютой контрагента ({1}). "
                        + "Выберите соответствующий способ оплаты.",
                        [frm.doc.cash_account_currency, frm.doc.party_currency])
                });
            }
        }
    }
});

function get_party_name_field(party_type) {
    return { Customer: "customer_name", Supplier: "supplier_name",
             Shareholder: "title", Employee: "employee_name" }[party_type] || null;
}