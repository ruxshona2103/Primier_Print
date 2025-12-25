frappe.ui.form.on('Purchase Invoice', {
    // 1. FORM YUKLANGANDA
    refresh: function(frm) {
        if (frm.doc.docstatus === 0 && !frm.doc.custom_transport_cost) {
            fetch_details_from_po(frm);
        }
    },

    // 2. LCV VALYUTASI O'ZGARSA -> KURSNI TOPIB KELISH (YANGI)
    custom_lcv_currency: function(frm) {
        get_lcv_exchange_rate(frm);
    },

    // 3. POSTING DATE O'ZGARSA -> KURSNI YANGILASH (YANGI)
    posting_date: function(frm) {
        if (frm.doc.custom_lcv_currency) {
            get_lcv_exchange_rate(frm);
        }
    },

    // 4. SUBMIT QILISHDAN OLDIN
    before_submit: function(frm) {
        return new Promise((resolve, reject) => {
            let items_html = '';
            let has_po_pr = false;

            $.each(frm.doc.items || [], function(i, item) {
                if (item.purchase_order || item.purchase_receipt) {
                    has_po_pr = true;
                    items_html += `
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.item_name}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;"><b>${format_currency(item.rate, frm.doc.currency)}</b></td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">${format_currency(item.amount, frm.doc.currency)}</td>
                        </tr>`;
                }
            });

            if (!has_po_pr) { resolve(); return; }

            let d = new frappe.ui.Dialog({
                title: __('Narxlarni Tasdiqlang'),
                indicator: 'blue',
                fields: [{
                    fieldtype: 'HTML',
                    options: `
                        <div style="margin-bottom: 20px;">
                            <h4 style="margin-top: 0; color: #2490ef;">📋 Joriy Narxlar</h4>
                            <p style="color: #555;">PO/PR dan kelgan narxlar bilan davom etasizmi?</p>
                            <table style="width: 100%; border-collapse: collapse;">
                                <thead><tr style="background: #f5f7fa;"><th style="padding: 10px;">Item</th><th style="padding: 10px; text-align: right;">Narx</th><th style="padding: 10px; text-align: right;">Summa</th></tr></thead>
                                <tbody>${items_html}</tbody>
                                <tfoot><tr style="background: #f5f7fa; font-weight: bold;"><td colspan="2" style="padding: 12px;">JAMI:</td><td style="padding: 12px; text-align: right;">${format_currency(frm.doc.grand_total, frm.doc.currency)}</td></tr></tfoot>
                            </table>
                        </div>`
                }],
                primary_action_label: __('✅ Ha, Tasdiqlayman'),
                secondary_action_label: __('❌ Yo\'q, O\'zgartiraman'),
                primary_action: () => { d.hide(); resolve(); },
                secondary_action: () => { d.hide(); reject(); frappe.show_alert({message: __('Narxlarni o\'zgartiring'), indicator: 'orange'}, 5); }
            });
            d.show();
            d.$wrapper.find('.modal-header .close').on('click', () => reject());
        });
    }
});

// --- YORDAMCHI FUNKSIYALAR ---

// A. Kursni olish funksiyasi (ERPNext yadrosidan foydalanadi)
// ... (Refresh va Before Submit qismlari o'zgarishsiz qoladi) ...

// --- YORDAMCHI FUNKSIYALAR ---

function get_lcv_exchange_rate(frm) {
    if (!frm.doc.custom_lcv_currency || !frm.doc.company) return;

    // Kompaniyaning asosiy valyutasini olamiz (Bu safar USD)
    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
        let company_currency = r.default_currency; // USD
        let lcv_currency = frm.doc.custom_lcv_currency; // Masalan UZS

        if (lcv_currency == company_currency) {
            frm.set_value('custom_lcv_exchange_rate', 1.0);
            return;
        }

        // SENIOR TRICK:
        // Agar kompaniya USD bo'lsa va biz UZS tanlasak,
        // bizga "1 USD necha so'm?" degan kurs kerak (masalan 12800).
        // Shuning uchun 'from' ga Base, 'to' ga LCV currency beramiz.

        frappe.call({
            method: "erpnext.setup.utils.get_exchange_rate",
            args: {
                transaction_date: frm.doc.posting_date || frappe.datetime.now_date(),
                from_currency: company_currency, // USD
                to_currency: lcv_currency        // UZS
            },
            callback: function(r) {
                if (r.message) {
                    frm.set_value('custom_lcv_exchange_rate', r.message);
                    frappe.msgprint({
                        title: __('Kurs Yangilandi'),
                        message: __(`1 ${company_currency} = ${r.message} ${lcv_currency}`),
                        indicator: 'green'
                    });
                }
            }
        });
    });
}

// ... (fetch_details_from_po funksiyasi o'zgarishsiz qoladi) ...
}

// B. PO dan ma'lumot olish funksiyasi
function fetch_details_from_po(frm) {
    let po_name = null;
    if (frm.doc.items && frm.doc.items.length > 0) {
        for (let item of frm.doc.items) {
            if (item.purchase_order) {
                po_name = item.purchase_order;
                break;
            }
        }
    }

    if (po_name) {
        frappe.db.get_value('Purchase Order', po_name,
            ['custom_transport_cost'],
            (r) => {
                if (r && r.custom_transport_cost) {
                    frm.set_value('custom_transport_cost', r.custom_transport_cost);
                }
            }
        );
    }
}
