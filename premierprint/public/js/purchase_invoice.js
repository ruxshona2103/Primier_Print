frappe.ui.form.on('Purchase Invoice', {
    // 1. FORM YUKLANGANDA
    refresh: function(frm) {
        // Faqat yangi (Draft) va transport narxi kiritilmagan bo'lsa, PO dan tortamiz
        if (frm.doc.docstatus === 0 && !frm.doc.custom_transport_cost) {
            fetch_details_from_po(frm);
        }
    },

    // 2. LCV VALYUTASI O'ZGARSA -> KURSNI YANGILASH
    custom_lcv_currency: function(frm) {
        get_lcv_exchange_rate(frm);
    },

    // 3. POSTING DATE O'ZGARSA -> KURSNI YANGILASH
    posting_date: function(frm) {
        if (frm.doc.custom_lcv_currency) {
            get_lcv_exchange_rate(frm);
        }
    },

    // 4. SUBMIT QILISHDAN OLDIN (Narxni Tasdiqlash Dialog)
    // Dialog HAR SAFAR ochiladi - narxlarni tasdiqlash uchun
    before_submit: function(frm) {
        return new Promise((resolve, reject) => {
            // PO/PR ga bog'liq itemlarni topish
            let items_with_po_pr = [];
            $.each(frm.doc.items || [], function(i, item) {
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

// Narxni Tasdiqlash Dialog
function show_price_verification_dialog(frm, dialog_data, resolve, reject) {
    let d = new frappe.ui.Dialog({
        title: __('Narxlarni Tasdiqlash'),
        indicator: 'blue',
        size: 'large',  // Kattaroq dialog
        fields: [
            {
                fieldtype: 'HTML',
                options: `
                    <div style="margin-bottom: 15px;">
                        <h4 style="margin: 0 0 10px 0; color: #2490ef;">📋 Narxlarni Tekshiring</h4>
                        <p style="color: #666; margin: 0;">
                            Agar narx o'zgargan bo'lsa, yangi narxni kiriting va "Tasdiqlash va Submit" bosing.
                            Aks holda, "Yo'q, O'zgartiraman" tugmasini bosing.
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
        primary_action_label: __('✅ Tasdiqlash va Submit'),
        secondary_action_label: __('❌ Tasdiqlamasdan davom etish'),
        primary_action: () => {
            // Jadvaldagi yangi narxlarni olish va o'zgarishni tekshirish
            let updated_items = [];
            let is_changed = false;

            dialog_data.forEach((item, index) => {
                let new_rate_input = d.$wrapper.find(`#new_rate_${index}`);
                let new_rate = parseFloat(new_rate_input.val()) || item.current_rate;

                // Narx o'zgarganini tekshirish
                if (Math.abs(new_rate - item.current_rate) > 0.001) {
                    is_changed = true;
                }

                updated_items.push({
                    idx: item.idx,
                    new_rate: new_rate
                });
            });

            // Formadagi narxlarni yangilash
            updated_items.forEach(updated_item => {
                let form_item = frm.doc.items.find(i => i.idx === updated_item.idx);
                if (form_item) {
                    form_item.rate = updated_item.new_rate;
                    // Recalculate amount
                    form_item.amount = flt(form_item.rate) * flt(form_item.qty);
                }
            });

            // Refresh items table
            frm.refresh_field('items');

            // Calculate totals
            frm.script_manager.trigger("calculate_taxes_and_totals");

            // Narx o'zgargan bo'lsa avval saqlab olamiz
            const continue_after_save = is_changed ? frm.save() : Promise.resolve();

            continue_after_save.then(() => {
                d.hide();
                resolve();
            }).catch(err => {
                frappe.msgprint({
                    title: __('Xatolik'),
                    message: __('Saqlashda xatolik: {0}', [err.message || err]),
                    indicator: 'red'
                });
                d.hide();
                reject(err);
            });
        },
        secondary_action: () => {
            d.hide();
            frappe.show_alert({
                message: __('Narx tasdiqlash stagesiz davom etyapti'),
                indicator: 'orange'
            }, 5);
            resolve();
        }
    });

    // Dialog ko'rsatish
    d.show();

    // X tugmasi bosilganda - dialog yopiladi, keyingi submit da qayta ochiladi
    d.$wrapper.find('.modal-header .close').on('click', () => {
        d.hide();
        frappe.show_alert({
            message: __('Narx tasdiqlash bosqichi o\'tkazib yuborildi'),
            indicator: 'orange'
        }, 5);
        resolve();
    });

    // Narx o'zgartirilganda summa avtomatik hisoblash
    setTimeout(() => {
        d.$wrapper.find('.new-rate-input').on('input', function() {
            let index = $(this).data('index');
            let qty = $(this).data('qty');
            let new_rate = parseFloat($(this).val()) || 0;
            let new_amount = qty * new_rate;

            // Summa ni yangilash
            d.$wrapper.find(`#amount_${index}`).html(
                format_currency(new_amount, frm.doc.currency)
            );
        });
    }, 100);
}

// Jadval HTML yaratish
function generate_items_table_html(items, currency) {
    let html = `
        <div style="overflow-x: auto; max-height: 500px; overflow-y: auto;">
            <table class="table table-bordered" style="width: 100%; margin: 0;">
                <thead style="background: #f5f7fa; position: sticky; top: 0; z-index: 10;">
                    <tr>
                        <th style="padding: 10px; min-width: 120px;">Item Code</th>
                        <th style="padding: 10px; min-width: 180px;">Item Name</th>
                        <th style="padding: 10px; text-align: right; min-width: 80px;">Qty</th>
                        <th style="padding: 10px; text-align: right; min-width: 120px;">Joriy Narx</th>
                        <th style="padding: 10px; text-align: right; min-width: 130px;">O'zgartirilgan Narx</th>
                        <th style="padding: 10px; text-align: right; min-width: 120px;">Summa</th>
                    </tr>
                </thead>
                <tbody>
    `;

    items.forEach((item, index) => {
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
                    <span style="color: #666;">${format_currency(item.current_rate, currency)}</span>
                </td>
                <td style="padding: 8px; vertical-align: middle;">
                    <input
                        type="number"
                        id="new_rate_${index}"
                        class="form-control new-rate-input"
                        value="${item.new_rate}"
                        step="0.01"
                        data-index="${index}"
                        data-qty="${item.qty}"
                        style="text-align: right; font-weight: bold; color: #2490ef;"
                    />
                </td>
                <td style="padding: 8px; text-align: right; vertical-align: middle;">
                    <span id="amount_${index}" style="font-weight: bold; color: #155724;">
                        ${format_currency(item.new_amount, currency)}
                    </span>
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
