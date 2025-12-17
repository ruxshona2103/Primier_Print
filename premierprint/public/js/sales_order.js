frappe.ui.form.on('Sales Order Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];

        if (!row.item_code) return;

        // Eng oxirgi Sales Invoice-dan narx olish
        frappe.call({
            method: 'premierprint.utils.pricing.get_last_sales_price',
            args: {
                item_code: row.item_code,
                customer: frm.doc.customer
            },
            callback: function(r) {
                if (r.message && r.message.rate) {
                    frappe.model.set_value(cdt, cdn, 'rate', r.message.rate);

                    // Ma'lumot ko'rsatish
                    frappe.show_alert({
                        message: __('Eng oxirgi narx ({0}): {1}', [
                            r.message.date || 'Noma\'lum sana',
                            format_currency(r.message.rate, frm.doc.currency)
                        ]),
                        indicator: 'blue'
                    }, 3);
                }
            }
        });
    }
});
