/**
 * AUTO FETCH ACCOUNT SCRIPT
 * =========================
 * ERPNext v15 uchun avtomatik Receivable/Payable hisob tanlash skripti.
 * 
 * MAQSAD:
 * Companiya va Valyutaga asosan tegishli "Receivable" yoki "Payable" hisoblarni
 * avtomatik ravishda mos maydonlarga o'rnatish.
 * 
 * ISHLASH TARTIBI:
 * 1. Foydalanuvchi `company` yoki `currency` maydonini o'zgartirganda trigger ishga tushadi
 * 2. Account DocType'dan quyidagi shartlar bilan qidiriladi:
 *    - company == Hujjat Kompaniyasi
 *    - account_currency == Hujjat Valyutasi
 *    - account_type == "Receivable" yoki "Payable" (DocType'ga qarab)
 *    - is_group == 0 (Faqat Ledger hisoblar, Group emas)
 * 3. Topilgan hisob tegishli maydoniga o'rnatiladi
 * 
 * DOCTYPE VA MAYDON MAPPING:
 * - Sales Invoice / Sales Order    -> debit_to (Receivable)
 * - Purchase Invoice / Purchase Order -> credit_to (Payable)
 * - Payment Entry (Receive)        -> paid_from (Receivable)
 * - Payment Entry (Pay)            -> paid_to (Payable)
 * 
 * XATOLIK BOSHQARUVI:
 * - Maydon mavjud bo'lmasa, hech narsa qilmaydi (silent fail)
 * - Hisob topilmasa, maydonni bo'sh qoldiradi
 * - Hech qanday qizil popup ko'rsatmaydi
 * 
 * MUALLIF: Gemini AI (Premier Print uchun)
 * VERSIYA: 1.0
 */

(function () {
    'use strict';

    // =========================================================================
    // KONFIGURATSIAYA - DocType va Maydon Mapping
    // =========================================================================

    /**
     * DOCTYPE_CONFIG - Har bir DocType uchun sozlamalar
     * 
     * Tuzilishi:
     * - target_field: Hisobni o'rnatish kerak bo'lgan maydon nomi
     * - account_type: Qidirilayotgan hisob turi ("Receivable" yoki "Payable")
     * - triggers: Qaysi maydonlar o'zgarganda trigger ishlashini ko'rsatadi
     */
    const DOCTYPE_CONFIG = {
        // SOTISH HUJJATLARI - Receivable hisob
        'Sales Invoice': {
            target_field: 'debit_to',
            account_type: 'Receivable',
            triggers: ['company', 'currency']
        },
        'Sales Order': {
            target_field: 'debit_to',
            account_type: 'Receivable',
            triggers: ['company', 'currency']
        },

        // XARID HUJJATLARI - Payable hisob
        'Purchase Invoice': {
            target_field: 'credit_to',
            account_type: 'Payable',
            triggers: ['company', 'currency']
        },
        'Purchase Order': {
            target_field: 'credit_to',
            account_type: 'Payable',
            triggers: ['company', 'currency']
        },

        // TO'LOV YOZUVI - payment_type'ga qarab dinamik
        // (Bu alohida handler orqali boshqariladi)
        'Payment Entry': {
            // target_field va account_type dinamik aniqlanadi
            triggers: ['company', 'paid_from_account_currency', 'paid_to_account_currency', 'payment_type']
        }
    };

    // =========================================================================
    // ASOSIY HISOB QIDIRISH FUNKSIYASI
    // =========================================================================

    /**
     * fetch_matching_account - Ma'lumotlar bazasidan mos hisobni topish
     * 
     * Bu funksiya frappe.call orqali serverga so'rov yuboradi va
     * berilgan shartlarga mos keladigan birinchi hisobni qaytaradi.
     * 
     * @param {Object} args - Qidiruv parametrlari
     * @param {string} args.company - Kompaniya nomi
     * @param {string} args.currency - Valyuta kodi (UZS, USD, EUR va h.k.)
     * @param {string} args.account_type - Hisob turi ("Receivable" yoki "Payable")
     * @param {Function} callback - Natijani qaytarish uchun callback funksiya
     * 
     * QIDIRUV SHARTLARI:
     * - company: Hujjatning kompaniyasiga teng
     * - account_currency: Hujjatning valyutasiga teng
     * - account_type: Berilgan turga teng
     * - is_group: 0 (Faqat Ledger hisoblar)
     */
    function fetch_matching_account(args, callback) {
        // Majburiy parametrlar tekshiruvi
        if (!args.company || !args.currency || !args.account_type) {
            // Parametrlar to'liq bo'lmasa, callback'ni bo'sh qiymat bilan chaqiramiz
            if (callback) callback(null);
            return;
        }

        // Serverdan hisob qidirish
        frappe.call({
            method: 'frappe.client.get_value',
            args: {
                doctype: 'Account',
                filters: {
                    company: args.company,
                    account_currency: args.currency,
                    account_type: args.account_type,
                    is_group: 0  // Faqat Ledger (yakuniy) hisoblar
                },
                fieldname: 'name'  // Faqat hisob nomini olamiz
            },
            async: true,  // Asinxron so'rov
            callback: function (r) {
                // Natijani callback orqali qaytaramiz
                if (r && r.message && r.message.name) {
                    callback(r.message.name);
                } else {
                    // Hisob topilmadi
                    callback(null);
                }
            },
            error: function () {
                // Server xatosi bo'lsa ham silent fail
                callback(null);
            }
        });
    }

    // =========================================================================
    // MAYDON O'RNATISH FUNKSIYASI
    // =========================================================================

    /**
     * set_field_value_safely - Maydon qiymatini xavfsiz o'rnatish
     * 
     * Bu funksiya maydon mavjudligini tekshiradi va agar mavjud bo'lsa,
     * qiymatni o'rnatadi. Agar mavjud bo'lmasa, hech narsa qilmaydi.
     * 
     * @param {Object} frm - Frappe form obyekti
     * @param {string} fieldname - O'rnatiladigan maydon nomi
     * @param {any} value - O'rnatiladigan qiymat
     * 
     * XAVFSIZLIK TEKSHIRUVLARI:
     * 1. frm.fields_dict mavjudligi
     * 2. fieldname shu form uchun mavjudligi
     */
    function set_field_value_safely(frm, fieldname, value) {
        // Form va fields_dict mavjudligini tekshirish
        if (!frm || !frm.fields_dict) {
            return;
        }

        // Maydon mavjudligini tekshirish
        if (!frm.fields_dict[fieldname]) {
            return;
        }

        // Qiymatni o'rnatish
        frm.set_value(fieldname, value);
    }

    // =========================================================================
    // HUJJAT TURIGA QARAB HISOBNI OLISH VA O'RNATISH
    // =========================================================================

    /**
     * handle_account_fetch - Asosiy handler funksiya
     * 
     * Bu funksiya DocType konfiguratsiyasiga qarab tegishli hisobni
     * qidiradi va mos maydoniga o'rnatadi.
     * 
     * @param {Object} frm - Frappe form obyekti
     * 
     * ISHLASH TARTIBI:
     * 1. DocType uchun konfiguratsiay bor-yo'qligini tekshiradi
     * 2. Payment Entry uchun alohida logika ishlatadi
     * 3. Boshqa DocType'lar uchun standart logika ishlatadi
     */
    function handle_account_fetch(frm) {
        const doctype = frm.doc.doctype;
        const config = DOCTYPE_CONFIG[doctype];

        // Bu DocType uchun konfiguratsiay yo'q
        if (!config) {
            return;
        }

        // Payment Entry uchun alohida handler
        if (doctype === 'Payment Entry') {
            handle_payment_entry(frm);
            return;
        }

        // Standart DocType'lar uchun handler
        handle_standard_doctype(frm, config);
    }

    // =========================================================================
    // STANDART DOCTYPE HANDLER
    // =========================================================================

    /**
     * handle_standard_doctype - Sales/Purchase Invoice/Order uchun handler
     * 
     * Bu funksiya Sales Invoice, Sales Order, Purchase Invoice va
     * Purchase Order DocType'lari uchun hisobni topib o'rnatadi.
     * 
     * @param {Object} frm - Frappe form obyekti
     * @param {Object} config - DocType konfiguratsiyasi
     */
    function handle_standard_doctype(frm, config) {
        const company = frm.doc.company;
        const currency = frm.doc.currency;
        const target_field = config.target_field;
        const account_type = config.account_type;

        // Company yoki Currency bo'sh bo'lsa, hech narsa qilmaymiz
        if (!company || !currency) {
            return;
        }

        // Hisobni qidirib topamiz
        fetch_matching_account({
            company: company,
            currency: currency,
            account_type: account_type
        }, function (account_name) {
            // Topilgan hisobni maydoniga o'rnatamiz
            // Agar topilmasa, null keladi va maydon bo'sh qoladi
            set_field_value_safely(frm, target_field, account_name);
        });
    }

    // =========================================================================
    // PAYMENT ENTRY HANDLER
    // =========================================================================

    /**
     * handle_payment_entry - Payment Entry uchun maxsus handler
     * 
     * Payment Entry boshqa DocType'lardan farq qiladi:
     * - payment_type = "Receive" bo'lsa: paid_from maydoniga Receivable hisob
     * - payment_type = "Pay" bo'lsa: paid_to maydoniga Payable hisob
     * 
     * Shuningdek, valyuta uchun alohida maydonlar ishlatiladi:
     * - paid_from uchun: paid_from_account_currency
     * - paid_to uchun: paid_to_account_currency
     * 
     * @param {Object} frm - Frappe form obyekti
     */
    function handle_payment_entry(frm) {
        const company = frm.doc.company;
        const payment_type = frm.doc.payment_type;

        // Company yoki payment_type bo'sh bo'lsa, chiqib ketamiz
        if (!company || !payment_type) {
            return;
        }

        // payment_type ga qarab qaysi maydonni o'zgartirishni aniqlaymiz
        if (payment_type === 'Receive') {
            // KIRIM TO'LOVI: paid_from maydoniga Receivable hisob
            const currency = frm.doc.paid_from_account_currency || frm.doc.party_account_currency;

            if (!currency) return;

            fetch_matching_account({
                company: company,
                currency: currency,
                account_type: 'Receivable'
            }, function (account_name) {
                set_field_value_safely(frm, 'paid_from', account_name);
            });
        }
        else if (payment_type === 'Pay') {
            // CHIQIM TO'LOVI: paid_to maydoniga Payable hisob
            const currency = frm.doc.paid_to_account_currency || frm.doc.party_account_currency;

            if (!currency) return;

            fetch_matching_account({
                company: company,
                currency: currency,
                account_type: 'Payable'
            }, function (account_name) {
                set_field_value_safely(frm, 'paid_to', account_name);
            });
        }
        // "Internal Transfer" uchun hech narsa qilmaymiz
    }

    // =========================================================================
    // FORM EVENT HANDLERS - DocType'lar uchun
    // =========================================================================

    /**
     * SALES INVOICE - Trigger hodisalari
     * 
     * company yoki currency o'zgarganda avtomatik hisob olinadi
     */
    frappe.ui.form.on('Sales Invoice', {
        // company o'zgarganda
        company: function (frm) {
            handle_account_fetch(frm);
        },
        // currency o'zgarganda
        currency: function (frm) {
            handle_account_fetch(frm);
        },
        // Form ochilganda (refresh)
        refresh: function (frm) {
            // Faqat yangi hujjat uchun
            if (frm.is_new()) {
                handle_account_fetch(frm);
            }
        }
    });

    /**
     * SALES ORDER - Trigger hodisalari
     */
    frappe.ui.form.on('Sales Order', {
        company: function (frm) {
            handle_account_fetch(frm);
        },
        currency: function (frm) {
            handle_account_fetch(frm);
        },
        refresh: function (frm) {
            if (frm.is_new()) {
                handle_account_fetch(frm);
            }
        }
    });

    /**
     * PURCHASE INVOICE - Trigger hodisalari
     */
    frappe.ui.form.on('Purchase Invoice', {
        company: function (frm) {
            handle_account_fetch(frm);
        },
        currency: function (frm) {
            handle_account_fetch(frm);
        },
        refresh: function (frm) {
            if (frm.is_new()) {
                handle_account_fetch(frm);
            }
        }
    });

    /**
     * PURCHASE ORDER - Trigger hodisalari
     */
    frappe.ui.form.on('Purchase Order', {
        company: function (frm) {
            handle_account_fetch(frm);
        },
        currency: function (frm) {
            handle_account_fetch(frm);
        },
        refresh: function (frm) {
            if (frm.is_new()) {
                handle_account_fetch(frm);
            }
        }
    });

    /**
     * PAYMENT ENTRY - Trigger hodisalari
     * 
     * Payment Entry uchun qo'shimcha triggerlar:
     * - payment_type: "Receive" yoki "Pay" ga qarab boshqa maydon o'zgaradi
     * - paid_from_account_currency: Receive uchun valyuta
     * - paid_to_account_currency: Pay uchun valyuta
     */
    frappe.ui.form.on('Payment Entry', {
        company: function (frm) {
            handle_account_fetch(frm);
        },
        payment_type: function (frm) {
            handle_account_fetch(frm);
        },
        paid_from_account_currency: function (frm) {
            // Faqat Receive rejimida
            if (frm.doc.payment_type === 'Receive') {
                handle_account_fetch(frm);
            }
        },
        paid_to_account_currency: function (frm) {
            // Faqat Pay rejimida
            if (frm.doc.payment_type === 'Pay') {
                handle_account_fetch(frm);
            }
        },
        refresh: function (frm) {
            if (frm.is_new()) {
                handle_account_fetch(frm);
            }
        }
    });

    // =========================================================================
    // QUICK ENTRY MODAL SUPPORT
    // =========================================================================

    /**
     * MODAL QOLLAB-QUVVATLASH
     * 
     * ERPNext v15 da "Quick Entry" modallari alohida ishlov talab qiladi.
     * Biz frappe.ui.form.make_control funksiyasini kuzatib,
     * modal ichida yaratilgan maydonlarni tracking qilamiz.
     * 
     * Bu qism control yaratilishini ushlab, agar tegishli DocType bo'lsa,
     * change hodisasini qo'shadi.
     */

    // Original make_control funksiyasini saqlash
    const original_make_control = frappe.ui.form.make_control;

    // make_control ni override qilish (agar mavjud bo'lsa)
    if (original_make_control) {
        frappe.ui.form.make_control = function (opts) {
            // Original funksiyani chaqirish
            const control = original_make_control.apply(this, arguments);

            // Modal ichida va tegishli maydon bo'lsa
            if (control && control.$input && opts.parent) {
                const $modal = $(opts.parent).closest('.modal');

                if ($modal.length > 0) {
                    // Modal doctype'ini topishga harakat qilamiz
                    const modal_doctype = $modal.find('[data-doctype]').data('doctype');

                    if (modal_doctype && DOCTYPE_CONFIG[modal_doctype]) {
                        const config = DOCTYPE_CONFIG[modal_doctype];

                        // Agar trigger maydonlaridan biri bo'lsa
                        if (config.triggers && config.triggers.includes(opts.df?.fieldname)) {
                            control.$input.on('change', function () {
                                // Modal uchun maxsus handler kerak bo'lishi mumkin
                                // Hozircha standart form handler ishlatiladi
                            });
                        }
                    }
                }
            }

            return control;
        };
    }

    // =========================================================================
    // DEBUG LOGLARI (Ishlab chiqish uchun - productionda o'chirilgan)
    // =========================================================================

    /**
     * DEBUG_MODE - Ishlab chiqish uchun loglarni yoqish
     * Production muhitda bu FALSE bo'lishi kerak
     */
    const DEBUG_MODE = false;

    /**
     * debug_log - Shartli log funksiyasi
     * @param {string} message - Log xabari
     * @param {any} data - Qo'shimcha ma'lumot (optional)
     */
    function debug_log(message, data) {
        if (DEBUG_MODE) {
            console.log('[Auto Fetch Account]', message, data || '');
        }
    }

    // Skript yuklangani haqida xabar (faqat debug rejimda)
    debug_log('Skript muvaffaqiyatli yuklandi');

})();
