/**
 * Purchase Invoice Client Script - Narxni Tasdiqlash
 * 
 * MAQSAD: Submit qilishdan oldin foydalanuvchiga narxlarni ko'rsatish (Read-Only)
 * 
 * MANTIQ:
 * 1. custom_price_verified = 1 bo'lsa -> submit davom etadi
 * 2. Aks holda -> Dialog ochiladi
 * 3. "Tasdiqlash va Submit" -> custom_price_verified = 1 qilib submit
 * 4. "Yo'q, O'zgartiraman" -> Dialog yopiladi, user formada o'zgartiradi
 */

frappe.ui.form.on('Purchase Invoice', {
    // Form yuklanganda
    refresh: function (frm) {
        // Draft bo'lsa va transport narxi kiritilmagan bo'lsa
        if (frm.doc.docstatus === 0 && !frm.doc.custom_transport_cost) {
            fetch_details_from_po(frm);
        }
    },

    // LCV valyutasi o'zgarsa
    custom_lcv_currency: function (frm) {
        get_lcv_exchange_rate(frm);
    },

    // Posting date o'zgarsa
    posting_date: function (frm) {
        if (frm.doc.custom_lcv_currency) {
            get_lcv_exchange_rate(frm);
        }
    },

    // BEFORE_SUBMIT - Narxlarni Ko'rsatish Dialogi
    before_submit: function (frm) {
        // Agar allaqachon tasdiqlangan bo'lsa - davom et
        if (frm.doc.custom_price_verified == 1) {
            return; // Submit davom etadi
        }

        // Submit to'xtatish
        frappe.validated = false;

        // Itemlarni tekshirish
        let all_items = frm.doc.items || [];
        if (all_items.length === 0) {
            frappe.validated = true;
            return;
        }

        // Item kodlarini yig'ish
        let item_codes = all_items.map(item => item.item_code);

        // API orqali so'nggi xarid narxlarini olish
        frappe.call({
            method: 'premierprint.api.purchase_invoice_api.get_last_purchase_prices',
            args: { items: JSON.stringify(item_codes) },
            freeze: true,
            freeze_message: __('Narxlar yuklanmoqda...'),
            callback: function (r) {
                if (r.message) {
                    let last_prices = r.message;

                    // Dialog uchun data tayyorlash
                    let dialog_data = all_items.map(item => ({
                        item_code: item.item_code,
                        item_name: item.item_name,
                        qty: item.qty,
                        joriy_narx: last_prices[item.item_code]?.price || 0,
                        joriy_narx_source: last_prices[item.item_code]?.source || 'Yangi',
                        faktura_narx: item.rate
                    }));

                    // Read-Only Dialog ko'rsatish
                    show_price_verification_dialog(frm, dialog_data);
                } else {
                    // API xatosi - dialog ko'rsatmasdan davom et
                    frm.set_value('custom_price_verified', 1);
                    frm.save('Submit');
                }
            },
            error: function (err) {
                console.error('Price fetch error:', err);
                frm.set_value('custom_price_verified', 1);
                frm.save('Submit');
            }
        });
    }
});

/**
 * Narxlarni Ko'rsatish Dialogi (Read-Only)
 */
function show_price_verification_dialog(frm, dialog_data) {
    let d = new frappe.ui.Dialog({
        title: __('Narxlarni Tasdiqlash'),
        indicator: 'blue',
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                options: `
                    <div style="margin-bottom: 15px; padding: 12px; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #2490ef;">
                        <h5 style="margin: 0 0 8px 0; color: #1a73e8;">
                            <i class="fa fa-info-circle"></i> Narxlarni Tekshiring
                        </h5>
                        <p style="color: #444; margin: 0; font-size: 13px;">
                            <b>Joriy Narx</b> — so'nggi xarid narxi (Purchase Receipt/Invoice dan).<br>
                            <b>Faktura Narxi</b> — ushbu fakturadagi narx.
                        </p>
                    </div>
                `
            },
            {
                fieldtype: 'HTML',
                fieldname: 'items_table',
                options: generate_readonly_table(dialog_data, frm.doc.currency)
            }
        ],
        primary_action_label: __('✅ Tasdiqlash va Submit'),
        secondary_action_label: __("❌ Yo'q, O'zgartiraman"),

        // PRIMARY: Tasdiqlash va Submit
        primary_action: () => {
            d.hide();
            frm.set_value('custom_price_verified', 1);
            frm.save('Submit').then(() => {
                frappe.show_alert({
                    message: __('Hujjat muvaffaqiyatli submit qilindi'),
                    indicator: 'green'
                }, 3);
            }).catch(err => {
                frappe.msgprint({
                    title: __('Xatolik'),
                    message: err.message || __('Submit qilishda xatolik'),
                    indicator: 'red'
                });
            });
        },

        // SECONDARY: Yo'q, O'zgartiraman - faqat dialogni yopish
        secondary_action: () => {
            d.hide();
            frappe.show_alert({
                message: __("Dialog yopildi. Narxlarni formada o'zgartiring va qaytadan Submit bosing."),
                indicator: 'orange'
            }, 5);
        }
    });

    d.show();

    // X tugmasi ham secondary action kabi ishlaydi
    d.$wrapper.find('.modal-header .close').off('click').on('click', () => {
        d.hide();
    });
}

/**
 * Read-Only Jadval (tahrirlash imkoniyati YO'Q)
 */
function generate_readonly_table(items, currency) {
    let html = `
        <div style="max-height: 350px; overflow-y: auto; border: 1px solid #d1d8dd; border-radius: 6px;">
            <table class="table table-bordered" style="width: 100%; margin: 0; font-size: 13px;">
                <thead style="background: #f8f9fa; position: sticky; top: 0;">
                    <tr>
                        <th style="padding: 10px;">Item Code</th>
                        <th style="padding: 10px;">Item Name</th>
                        <th style="padding: 10px; text-align: center;">Qty</th>
                        <th style="padding: 10px; text-align: right; background: #fff8e1;">📌 Joriy Narx</th>
                        <th style="padding: 10px; text-align: right; background: #e8f5e9;">📋 Faktura Narxi</th>
                        <th style="padding: 10px; text-align: center;">Farq</th>
                    </tr>
                </thead>
                <tbody>
    `;

    items.forEach((item) => {
        let diff = item.faktura_narx - item.joriy_narx;
        let diffPercent = item.joriy_narx > 0 ? ((diff / item.joriy_narx) * 100).toFixed(1) : 0;
        let diffClass = diff > 0 ? 'text-danger' : (diff < 0 ? 'text-success' : 'text-muted');
        let diffSign = diff > 0 ? '+' : '';
        let rowBg = Math.abs(diff) > 0.01 ? 'rgba(255, 243, 205, 0.2)' : '';

        html += `
            <tr style="background: ${rowBg};">
                <td style="padding: 8px;">
                    <code style="color: #1a73e8;">${item.item_code}</code>
                </td>
                <td style="padding: 8px;">${item.item_name}</td>
                <td style="padding: 8px; text-align: center;">
                    <span class="badge" style="background: #6c757d; color: white; padding: 3px 8px;">
                        ${format_number(item.qty, null, 2)}
                    </span>
                </td>
                <td style="padding: 8px; text-align: right; background: rgba(255, 248, 225, 0.3);">
                    <span style="color: #b8860b; font-weight: 500;">
                        ${item.joriy_narx > 0 ? format_currency(item.joriy_narx, currency) : '<em>Yangi</em>'}
                    </span>
                    <br><small style="color: #888; font-size: 10px;">${item.joriy_narx_source}</small>
                </td>
                <td style="padding: 8px; text-align: right; background: rgba(232, 245, 233, 0.3);">
                    <span style="color: #2e7d32; font-weight: 600;">
                        ${format_currency(item.faktura_narx, currency)}
                    </span>
                </td>
                <td style="padding: 8px; text-align: center;">
                    <span class="${diffClass}" style="font-weight: 600;">${diffSign}${diffPercent}%</span>
                </td>
            </tr>
        `;
    });

    html += `
                </tbody>
            </table>
        </div>
    `;

    return html;
}

// ==================== YORDAMCHI FUNKSIYALAR ====================

function get_lcv_exchange_rate(frm) {
    if (!frm.doc.custom_lcv_currency || !frm.doc.company) return;

    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
        let company_currency = r.default_currency;
        let lcv_currency = frm.doc.custom_lcv_currency;

        if (lcv_currency == company_currency) {
            frm.set_value('custom_lcv_exchange_rate', 1.0);
            return;
        }

        frappe.call({
            method: "erpnext.setup.utils.get_exchange_rate",
            args: {
                transaction_date: frm.doc.posting_date || frappe.datetime.now_date(),
                from_currency: company_currency,
                to_currency: lcv_currency
            },
            callback: function (r) {
                if (r.message) {
                    frm.set_value('custom_lcv_exchange_rate', r.message);
                }
            }
        });
    });
}

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
