// Copyright (c) 2025, abdulloh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Kassa", {

    refresh: function (frm) {
        frm.trigger("register_kassa_query");
        frm.trigger("register_kassa_to_query");

        frm.set_query("expense_account", function () {
            return {
                filters: {
                    company: frm.doc.company,
                    root_type: "Expense",
                    is_group: 0
                }
            };
        });

        // mode_of_payment is READ-ONLY — auto-derived from kassa account selection.
        frm.set_df_property("mode_of_payment", "read_only", 1);

        if (frm.doc.cash_account && frm.doc.company) {
            frm.trigger("update_balance");
        }
        if (frm.doc.cash_account_to && frm.doc.company) {
            frm.trigger("update_balance_to");
        }

        if (frm.doc.transaction_type === "Конвертация" && !frm.doc.exchange_rate) {
            frm.trigger("fetch_exchange_rate");
        }

        frm.trigger("update_balance_label");
        frm.trigger("apply_kassa_field_state");
    },

    // ─── Query Registration ───────────────────────────────────────────────────

    register_kassa_query: function (frm) {
        // Source kassa: only accounts belonging to the selected company
        frm.set_query("kassa", function () {
            return {
                query: "premierprint.premierprint.doctype.kassa.kassa.get_kassa_accounts",
                filters: { company: frm.doc.company || "" }
            };
        });
    },

    register_kassa_to_query: function (frm) {
        // Destination kassa: same company for now (cross-company deferred).
        // Uses get_kassa_accounts_to which shows company column in results.
        frm.set_query("kassa_to", function () {
            return {
                query: "premierprint.premierprint.doctype.kassa.kassa.get_kassa_accounts_to",
                filters: { company: frm.doc.company || "" }
            };
        });
    },

    // ─── Field State Guard ────────────────────────────────────────────────────

    apply_kassa_field_state: function (frm) {
        const has_company = !!(frm.doc.company);
        frm.set_df_property("kassa", "read_only", has_company ? 0 : 1);
        frm.set_df_property("kassa_to", "read_only", has_company ? 0 : 1);

        frm.set_df_property("kassa", "description",
            has_company ? "" : __("Сначала выберите компанию"));

        frm.refresh_fields(["kassa", "kassa_to"]);
    },

    // ─── Company Change ───────────────────────────────────────────────────────

    company: function (frm) {
        frm.set_value("kassa", "");
        frm.set_value("cash_account", "");
        frm.set_value("kassa_to", "");
        frm.set_value("cash_account_to", "");
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account_currency", "");
        frm.set_value("balance", 0);
        frm.set_value("balance_to", 0);
        frm.set_value("party", "");
        frm.set_value("expense_account", "");

        frm.trigger("register_kassa_query");
        frm.trigger("register_kassa_to_query");
        frm.trigger("apply_kassa_field_state");
    },

    // ─── CORE: kassa onchange (source visible drawer selector) ───────────────
    // kassa → cash_account mirror → Account-First chain:
    //   MoP reverse-lookup → currency derivation → balance update

    kassa: function (frm) {
        if (!frm.doc.kassa) {
            frm.set_value("cash_account", "");
            frm.set_value("mode_of_payment", "");
            frm.set_value("cash_account_currency", "");
            frm.set_value("balance", 0);
            return;
        }

        // Mirror: kassa IS the cash account
        frm.set_value("cash_account", frm.doc.kassa);

        // Step 1: Reverse-lookup MoP from source account
        frappe.call({
            method: "premierprint.premierprint.doctype.kassa.kassa.get_mop_for_account",
            args: { account: frm.doc.kassa, company: frm.doc.company },
            callback: function (r) {
                if (r.message) {
                    frm.set_value("mode_of_payment", r.message);
                } else {
                    frappe.msgprint({
                        title: __("Способ оплаты не найден"),
                        indicator: "orange",
                        message: __("Для счёта «{0}» не настроен способ оплаты. " +
                            "Проверьте настройки Mode of Payment.", [frm.doc.kassa])
                    });
                    frm.set_value("mode_of_payment", "");
                }
            }
        });

        // Step 2: Derive currency from Account GL record
        frappe.db.get_value("Account", frm.doc.kassa, "account_currency", function (r) {
            if (r && r.account_currency) {
                frm.set_value("cash_account_currency", r.account_currency);
                frm.trigger("validate_currency");
            }
        });

        // Step 3: Update source balance
        frm.trigger("update_balance");

        // Step 4: Reset destination when source changes
        if (in_list(["Перемещения", "Конвертация"], frm.doc.transaction_type)) {
            frm.set_value("kassa_to", "");
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
        }
    },

    // ─── CORE: kassa_to onchange (destination visible drawer selector) ────────
    // kassa_to → cash_account_to mirror.
    // No MoP lookup needed for destination — server validates account type directly.

    kassa_to: function (frm) {
        if (!frm.doc.kassa_to) {
            frm.set_value("cash_account_to", "");
            frm.set_value("balance_to", 0);
            return;
        }

        // Mirror: kassa_to IS the destination cash account
        frm.set_value("cash_account_to", frm.doc.kassa_to);

        // Update destination balance
        frm.trigger("update_balance_to");

        // For Conversion: auto-fetch rate and recalculate
        if (frm.doc.transaction_type === "Конвертация") {
            frm.trigger("fetch_exchange_rate");
            frm.trigger("calculate_conversion_amount");
        }
    },

    // ─── Balance Updaters ─────────────────────────────────────────────────────

    update_balance: function (frm) {
        if (frm.doc.cash_account && frm.doc.company) {
            frappe.call({
                method: "premierprint.premierprint.doctype.kassa.kassa.get_account_balance",
                args: { account: frm.doc.cash_account, company: frm.doc.company },
                callback: function (r) { frm.set_value("balance", r.message || 0); }
            });
        }
    },

    update_balance_to: function (frm) {
        if (frm.doc.cash_account_to) {
            // Destination may belong to a different company — derive company from account
            frappe.db.get_value("Account", frm.doc.cash_account_to, "company", function (r) {
                const company_to = (r && r.company) ? r.company : frm.doc.company;
                frappe.call({
                    method: "premierprint.premierprint.doctype.kassa.kassa.get_account_balance",
                    args: { account: frm.doc.cash_account_to, company: company_to },
                    callback: function (r2) { frm.set_value("balance_to", r2.message || 0); }
                });
            });
        }
    },

    // ─── Transaction Type Change ──────────────────────────────────────────────

    transaction_type: function (frm) {
        frm.set_value("party_type", "");
        frm.set_value("party", "");
        frm.set_value("expense_account", "");
        frm.set_value("party_name", "");
        frm.set_value("expense_account_name", "");
        frm.set_value("kassa", "");
        frm.set_value("cash_account", "");
        frm.set_value("mode_of_payment", "");
        frm.set_value("cash_account_currency", "");
        frm.set_value("balance", 0);
        frm.set_value("kassa_to", "");
        frm.set_value("cash_account_to", "");
        frm.set_value("balance_to", 0);
        frm.set_value("exchange_rate", 0);
        frm.set_value("debit_amount", 0);
        frm.set_value("credit_amount", 0);

        frm.trigger("register_kassa_query");
        frm.trigger("register_kassa_to_query");

        if (frm.doc.transaction_type === "Перемещения" && !frm.doc.company) {
            frappe.call({
                method: "frappe.client.get_value",
                args: { doctype: "Global Defaults", fieldname: "default_company" },
                callback: function (r) {
                    if (r.message && r.message.default_company) {
                        frm.set_value("company", r.message.default_company);
                        frm.trigger("register_kassa_query");
                        frm.trigger("register_kassa_to_query");
                        frm.trigger("apply_kassa_field_state");
                    }
                }
            });
        } else {
            frm.trigger("register_kassa_query");
            frm.trigger("apply_kassa_field_state");
        }

        if (frm.doc.transaction_type === "Конвертация") {
            frm.trigger("fetch_exchange_rate");
        }

        frm.trigger("update_balance_label");
    },

    // ─── Conversion Calculation ───────────────────────────────────────────────
    // Direction derived from cash_account_currency — name-agnostic.

    debit_amount: function (frm) { frm.trigger("calculate_conversion_amount"); },
    exchange_rate: function (frm) { frm.trigger("calculate_conversion_amount"); },

    calculate_conversion_amount: function (frm) {
        if (frm.doc.transaction_type !== "Конвертация") return;
        if (!frm.doc.debit_amount || !frm.doc.exchange_rate) return;

        const from_currency = frm.doc.cash_account_currency;
        if (!from_currency) return;

        if (from_currency === "UZS") {
            // UZS → USD: divide by exchange rate (e.g. 12500)
            frm.set_value("credit_amount",
                flt(flt(frm.doc.debit_amount) / flt(frm.doc.exchange_rate), 2));
        } else if (from_currency === "USD") {
            // USD → UZS: multiply by exchange rate
            frm.set_value("credit_amount",
                flt(flt(frm.doc.debit_amount) * flt(frm.doc.exchange_rate), 0));
        }
    },

    // ─── Exchange Rate Fetch ──────────────────────────────────────────────────

    fetch_exchange_rate: function (frm) {
        frappe.call({
            method: "premierprint.premierprint.doctype.kassa.kassa.get_exchange_rate",
            args: {
                from_currency: "USD",
                to_currency: "UZS",
                date: frm.doc.date || frappe.datetime.get_today()
            },
            callback: function (r) {
                if (r.message) frm.set_value("exchange_rate", r.message);
            }
        });
    },

    // ─── UI Label ────────────────────────────────────────────────────────────

    update_balance_label: function (frm) {
        const label = in_list(["Перемещения", "Конвертация"], frm.doc.transaction_type)
            ? "Остаток (откуда)" : "Остаток";
        frm.set_df_property("balance", "label", label);
        frm.refresh_field("balance");
    },

    // ─── Party Logic ──────────────────────────────────────────────────────────

    party_type: function (frm) {
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

    party: function (frm) {
        if (frm.doc.party && frm.doc.party_type) {
            const name_field = get_party_name_field(frm.doc.party_type);
            if (name_field) {
                frappe.db.get_value(frm.doc.party_type, frm.doc.party, name_field, function (r) {
                    if (r && r[name_field]) frm.set_value("party_name", r[name_field]);
                });
            }
            if (in_list(["Customer", "Supplier"], frm.doc.party_type)) {
                frappe.call({
                    method: "premierprint.premierprint.doctype.kassa.kassa.get_party_currency",
                    args: {
                        party_type: frm.doc.party_type,
                        party: frm.doc.party,
                        company: frm.doc.company
                    },
                    callback: function (r) {
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

    // ─── Currency Cross-Validation ────────────────────────────────────────────

    validate_currency: function (frm) {
        if (frm.doc.cash_account_currency && frm.doc.party_currency) {
            if (frm.doc.cash_account_currency !== frm.doc.party_currency) {
                frappe.validated = false;
                frappe.msgprint({
                    title: __("Ошибка валюты"),
                    indicator: "red",
                    message: __("Валюта кассы ({0}) не совпадает с валютой контрагента ({1}). " +
                        "Выберите соответствующий счет кассы.",
                        [frm.doc.cash_account_currency, frm.doc.party_currency])
                });
            }
        }
    }
});

function get_party_name_field(party_type) {
    return {
        Customer: "customer_name",
        Supplier: "supplier_name",
        Shareholder: "title",
        Employee: "employee_name"
    }[party_type] || null;
}
