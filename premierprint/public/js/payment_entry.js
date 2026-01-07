// your_app/public/js/payment_entry.js

frappe.ui.form.on('Payment Entry', {
    refresh: function(frm) {
        apply_strict_filters(frm);
    },
    mode_of_payment: function(frm) {
        apply_strict_filters(frm);
    },
    company: function(frm) {
        apply_strict_filters(frm);
    }
});

function apply_strict_filters(frm) {
    if (frm.doc.mode_of_payment && frm.doc.company) {
        // Mode of Payment turini serverdan qat'iy olish
        frappe.call({
            method: "frappe.client.get_value",
            args: {
                doctype: "Mode of Payment",
                filters: { name: frm.doc.mode_of_payment },
                fieldname: "type"
            },
            callback: function(r) {
                if (r.message && r.message.type) {
                    let target_type = r.message.type; // "Cash" yoki "Bank"

                    // Standart filtrni butunlay o'chirib, yangisini o'rnatamiz
                    frm.set_query('bank_account', function() {
                        return {
                            filters: {
                                "account_type": target_type, // Faqat bittasi: yo Bank, yo Cash
                                "company": frm.doc.company,
                                "is_group": 0
                            }
                        };
                    });
                }
            }
        });
    }
}
