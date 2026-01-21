frappe.ui.form.on('Purchase Invoice', {
    // 1. FORM YUKLANGANDA
    refresh: function (frm) {
        // Faqat yangi (Draft) va transport narxi kiritilmagan bo'lsa, PO dan tortamiz
        if (frm.doc.docstatus === 0 && !frm.doc.custom_transport_cost) {
            fetch_details_from_po(frm);
        }
    },

    // 2. LCV VALYUTASI O'ZGARSA -> KURSNI YANGILASH
    custom_lcv_currency: function (frm) {
        get_lcv_exchange_rate(frm);
    },

    // 3. POSTING DATE O'ZGARSA -> KURSNI YANGILASH
    posting_date: function (frm) {
        if (frm.doc.custom_lcv_currency) {
            get_lcv_exchange_rate(frm);
        }
    },

    // 4. SUBMIT QILISHDAN OLDIN (Narxni Tasdiqlash Dialog)
    // Dialog HAR SAFAR ochiladi - narxlarni tasdiqlash uchun
    before_submit: function (frm) {
        return new Promise((resolve, reject) => {
            // PO/PR ga bog'liq itemlarni topish
            let items_with_po_pr = [];
            $.each(frm.doc.items || [], function (i, item) {
                if (item.purchase_order || item.purchase_receipt) {
                    items_with_po_pr.push(item);
                }
            });

            // Agar PO/PR ga bog'liq item bo'lmasa, dialogsiz o'tkazamiz
            if (items_with_po_pr.length === 0) {
                resolve();
                return;
            }

            // Dialog uchun data tayyorlash
            // Joriy narxlarni ko'rsatadi (foydalanuvchi o'zgartirgan bo'lishi mumkin)
            let dialog_data = items_with_po_pr.map(item => ({
                idx: item.idx,
                item_code: item.item_code,
                item_name: item.item_name,
                qty: item.qty,
                current_rate: item.rate,  // Hozirgi narx (o'zgargan bo'lishi mumkin)
                current_amount: item.amount,
                new_rate: item.rate,  // Default qiymati joriy narx
                new_amount: item.amount  // Default qiymati joriy summa
            }));

            // Narxni Tasdiqlash Dialog - har safar ochiladi
            show_price_verification_dialog(frm, dialog_data, resolve, reject);
        });
    }
});

// --- YORDAMCHI FUNKSIYALAR ---

// Narxni Tasdiqlash Dialog - Faqat ko'rish uchun (Read-Only Summary)
function show_price_verification_dialog(frm, dialog_data, resolve, reject) {
    let d = new frappe.ui.Dialog({
        title: __('Narxlarni Tasdiqlash'),
        indicator: 'blue',
        size: 'large',
        fields: [
            {
                fieldtype: 'HTML',
                options: `
                    <div style="margin-bottom: 15px;">
                        <h4 style="margin: 0 0 10px 0; color: #2490ef;">📋 Narxlarni Tekshiring</h4>
                        <p style="color: #666; margin: 0;">
                            Quyidagi narxlar Items jadvalidagi joriy narxlardir.
                            Agar to'g'ri bo'lsa "Ha, tasdiqlayman" tugmasini bosing.
                            Narxni o'zgartirish uchun "Ha, o'zgartiraman" tugmasini bosing.
                        </p>
                    </div>
                `
            },
            {
                fieldtype: 'HTML',
                fieldname: 'items_table',
                options: generate_items_table_html(dialog_data, frm.doc.currency)
            }
        ],
        primary_action_label: __("✅ Ha, tasdiqlayman"),
        secondary_action_label: __("✏️ Ha, o'zgartiraman"),
        primary_action: () => {
            // Tasdiqlash - submit qilish
            d.hide();
            resolve();
        },
        secondary_action: () => {
            // Foydalanuvchi narxlarni o'zgartirmoqchi - Items jadvaliga fokus
            d.hide();

            // Items child table ga scroll va fokus
            scroll_and_focus_items_table(frm);

            // Submission ni to'xtatish (reject)
            reject();
        }
    });

    // Dialog ko'rsatish
    d.show();

    // X tugmasi bosilganda - submission to'xtatiladi
    d.$wrapper.find('.modal-header .close').on('click', () => {
        d.hide();
        reject();
    });
}

// Items child table ga scroll va fokus qilish
function scroll_and_focus_items_table(frm) {
    // Items section ga scroll
    let items_section = frm.fields_dict.items.$wrapper;
    if (items_section && items_section.length) {
        $('html, body').animate({
            scrollTop: items_section.offset().top - 100
        }, 300);

        // Birinchi row ning rate input ga fokus
        setTimeout(() => {
            let rate_field = items_section.find('.frappe-control[data-fieldname="rate"] input').first();
            if (rate_field.length) {
                rate_field.focus().select();
            }

            // Foydalanuvchiga xabar
            frappe.show_alert({
                message: __("Items jadvalida narxni o'zgartiring, keyin qayta Submit bosing"),
                indicator: 'blue'
            }, 5);
        }, 400);
    }
}

// Jadval HTML yaratish - Faqat ko'rish uchun (Read-Only)
function generate_items_table_html(items, currency) {
    let html = `
        <div style="overflow-x: auto; max-height: 500px; overflow-y: auto;">
            <table class="table table-bordered" style="width: 100%; margin: 0;">
                <thead style="background: #f5f7fa; position: sticky; top: 0; z-index: 10;">
                    <tr>
                        <th style="padding: 10px; min-width: 120px;">Item Code</th>
                        <th style="padding: 10px; min-width: 180px;">Item Name</th>
                        <th style="padding: 10px; text-align: right; min-width: 80px;">Qty</th>
                        <th style="padding: 10px; text-align: right; min-width: 120px;">Narx</th>
                        <th style="padding: 10px; text-align: right; min-width: 120px;">Summa</th>
                    </tr>
                </thead>
                <tbody>
    `;

    items.forEach((item) => {
        html += `
            <tr>
                <td style="padding: 8px; vertical-align: middle;">
                    <b>${item.item_code}</b>
                </td>
                <td style="padding: 8px; vertical-align: middle;">
                    ${item.item_name}
                </td>
                <td style="padding: 8px; text-align: right; vertical-align: middle;">
                    <span style="color: #666;">${format_number(item.qty, null, 2)}</span>
                </td>
                <td style="padding: 8px; text-align: right; vertical-align: middle;">
                    <span style="font-weight: bold; color: #2490ef;">${format_currency(item.current_rate, currency)}</span>
                </td>
                <td style="padding: 8px; text-align: right; vertical-align: middle;">
                    <span style="font-weight: bold; color: #155724;">${format_currency(item.current_amount, currency)}</span>
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

// A. Kursni olish funksiyasi (Universal)
function get_lcv_exchange_rate(frm) {
    if (!frm.doc.custom_lcv_currency || !frm.doc.company) return;

    // Kompaniyaning asosiy valyutasini olamiz (Senda USD)
    frappe.db.get_value('Company', frm.doc.company, 'default_currency', (r) => {
        let company_currency = r.default_currency; // USD
        let lcv_currency = frm.doc.custom_lcv_currency; // Masalan UZS

        // Agar valyutalar bir xil bo'lsa
        if (lcv_currency == company_currency) {
            frm.set_value('custom_lcv_exchange_rate', 1.0);
            return;
        }

        // KURS HISOBLASH (SENIOR LOGIC)
        // Senga "1 USD necha so'm?" degan kurs kerak (Masalan: 12800).
        // Shuning uchun from_currency ga USD (Base), to_currency ga UZS (LCV) beramiz.

        frappe.call({
            method: "erpnext.setup.utils.get_exchange_rate",
            args: {
                transaction_date: frm.doc.posting_date || frappe.datetime.now_date(),
                from_currency: company_currency, // USD
                to_currency: lcv_currency        // UZS
            },
            callback: function (r) {
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

// B. PO dan Transport narxini olish funksiyasi
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
                    frappe.show_alert({
                        message: __('Purchase Orderdan transport narxi yuklandi: ' + r.custom_transport_cost),
                        indicator: 'green'
                    });
                }
            }
        );
    }
}
