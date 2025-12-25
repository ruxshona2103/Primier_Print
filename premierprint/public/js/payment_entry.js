//frappe.ui.form.on('Payment Entry', {
//    // 1. refresh hodisasi
//    refresh: function(frm) {
//        frm.trigger('setup_account_filters');
//        frm.trigger('setup_party_logic');
//    },
//
//    // 2. party_type hodisasi
//    party_type: function(frm) {
//        frm.trigger('setup_party_logic');
//        // Party qiymatini tozalash
//        frm.set_value('party', '');
//    },
//
//    // 3. party hodisasi: Expense Category uchun hisob olib kelish
//    party: function(frm) {
//        if (frm.doc.party_type === 'Expense Category' && frm.doc.party) {
//            frm.trigger('load_expense_account');
//        }
//    },
//
//    // 4. payment_type hodisasi
//    payment_type: function(frm) {
//        if (frm.doc.party_type === 'Expense Category' && frm.doc.party) {
//            frm.trigger('load_expense_account');
//        }
//    },
//
//    // 5. company hodisasi
//    company: function(frm) {
//        frm.trigger('setup_account_filters');
//        frm.trigger('setup_party_logic');
//    },
//
//    // 6. mode_of_payment hodisasi
//    mode_of_payment: function(frm) {
//        frm.trigger('setup_account_filters');
//    },
//
//    // === CUSTOM FUNCTIONS ===
//
//    // Party Logic: Label va filtrlarni sozlash
//    setup_party_logic: function(frm) {
//        if (frm.doc.party_type === 'Expense Category') {
//            // Label'ni o'zgartirish
//            frm.set_df_property('party', 'label', 'Категория расхода');
//
//            // Party uchun filtr o'rnatish (faqat tanlangan kompaniyaga tegishli)
//            frm.set_query('party', function() {
//                let filters = {};
//                if (frm.doc.company) {
//                    filters.company = frm.doc.company;
//                }
//                return { filters: filters };
//            });
//        } else {
//            // Standart holatga qaytarish
//            frm.set_df_property('party', 'label', 'Party');
//        }
//    },
//
//    // Expense Account'ni yuklash
//    load_expense_account: function(frm) {
//        if (frm.doc.party_type === 'Expense Category' && frm.doc.party) {
//            frappe.db.get_value('Expense Category', frm.doc.party, 'expense_account', (r) => {
//                if (r && r.expense_account) {
//                    const expense_account = r.expense_account;
//
//                    // Payment Type'ga qarab to'g'ri maydonni to'ldirish
//                    if (frm.doc.payment_type === 'Pay') {
//                        // Chiqim: Paid To ga xarajat hisobini o'rnatish
//                        frm.set_value('paid_to', expense_account);
//                    } else if (frm.doc.payment_type === 'Receive') {
//                        // Kirim: Paid From ga xarajat hisobini o'rnatish
//                        frm.set_value('paid_from', expense_account);
//                    }
//
//                    frappe.show_alert({
//                        message: `Expense Account yuklandi: ${expense_account}`,
//                        indicator: 'green'
//                    });
//                }
//            });
//        }
//    },
//
//    // Account Filters: Paid To/From uchun
//    setup_account_filters: function(frm) {
//        if (frm.doc.company) {
//            let base_filters = {
//                'company': frm.doc.company,
//                'is_group': 0
//            };
//
//            // Mode of Payment asosida account_type filtrini qo'shish
//            let account_type = null;
//            if (frm.doc.mode_of_payment) {
//                if (frm.doc.mode_of_payment === 'Наличные') {
//                    account_type = 'Cash';
//                } else if (['Пластик', 'Терминал', 'Перечисления'].includes(frm.doc.mode_of_payment)) {
//                    account_type = 'Bank';
//                }
//            }
//
//            let fields = ['paid_to', 'paid_from'];
//            fields.forEach(field => {
//                frm.set_query(field, function() {
//                    let filters = { ...base_filters };
//                    if (account_type) {
//                        filters.account_type = account_type;
//                    }
//                    return { filters: filters };
//                });
//            });
//        }
//    }
//});
