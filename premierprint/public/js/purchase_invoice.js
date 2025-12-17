frappe.ui.form.on('Purchase Invoice', {
    before_submit: function(frm) {
        // Submit oldidan dialog ko'rsatish
        return new Promise((resolve, reject) => {

            // Narxlarni tayyorlash
            let items_html = '';
            let has_po_pr = false;

            $.each(frm.doc.items || [], function(i, item) {
                if (item.purchase_order || item.purchase_receipt) {
                    has_po_pr = true;
                    items_html += `
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #eee;">${item.item_name}</td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">
                                <b>${format_currency(item.rate, frm.doc.currency)}</b>
                            </td>
                            <td style="padding: 8px; border-bottom: 1px solid #eee; text-align: right;">
                                ${format_currency(item.amount, frm.doc.currency)}
                            </td>
                        </tr>
                    `;
                }
            });

            // Agar PO/PR dan kelgan itemlar bo'lmasa, oddiy submit
            if (!has_po_pr) {
                resolve();
                return;
            }

            // Tasdiqlov dialog
            let d = new frappe.ui.Dialog({
                title: __('Narxlarni Tasdiqlang'),
                indicator: 'blue',
                fields: [
                    {
                        fieldtype: 'HTML',
                        options: `
                            <div style="margin-bottom: 20px;">
                                <h4 style="margin-top: 0; color: #2490ef;">
                                    📋 Joriy Narxlar
                                </h4>
                                <p style="color: #555; margin-bottom: 15px;">
                                    Quyidagi narxlar bilan davom etasizmi?
                                </p>
                                <table style="width: 100%; border-collapse: collapse;">
                                    <thead>
                                        <tr style="background: #f5f7fa;">
                                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #2490ef;">Item</th>
                                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #2490ef;">Narx</th>
                                            <th style="padding: 10px; text-align: right; border-bottom: 2px solid #2490ef;">Summa</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        ${items_html}
                                    </tbody>
                                    <tfoot>
                                        <tr style="background: #f5f7fa; font-weight: bold;">
                                            <td style="padding: 12px; border-top: 2px solid #2490ef;" colspan="2">
                                                JAMI:
                                            </td>
                                            <td style="padding: 12px; text-align: right; border-top: 2px solid #2490ef;">
                                                ${format_currency(frm.doc.grand_total, frm.doc.currency)}
                                            </td>
                                        </tr>
                                    </tfoot>
                                </table>
                            </div>
                            <div style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; margin-top: 20px;">
                                <p style="margin: 0; color: #856404;">
                                    <b>⚠️ Diqqat:</b> "Ha" deb tasdiqlasangiz, invoice submit bo'ladi.
                                    <br>Agar narxlarni o'zgartirmoqchi bo'lsangiz, "Yo'q" tugmasini bosing.
                                </p>
                            </div>
                        `
                    }
                ],
                primary_action_label: __('✅ Ha, Tasdiqlaysiz'),
                secondary_action_label: __('❌ Yo\'q, O\'zgartiraman'),
                primary_action: function() {
                    d.hide();
                    resolve(); // Submit davom etsin
                },
                secondary_action: function() {
                    d.hide();
                    reject(); // Submit to'xtatilsin
                    frappe.show_alert({
                        message: __('Narxlarni o\'zgartiring va qayta submit qiling'),
                        indicator: 'orange'
                    }, 5);
                }
            });

            d.show();

            // Agar dialog yopilsa (X bosilsa) - to'xtatish
            d.$wrapper.find('.modal-header .close').on('click', function() {
                reject();
            });
        });
    }
});
