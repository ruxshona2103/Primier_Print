frappe.ui.form.on('Sales Order', {
    onload: function (frm) {
        // Yangi hujjat ochilganda standart seriyani bo'shatib turish yoki kompaniyaga qarab o'rnatish
        if (frm.is_new() && frm.doc.company) {
            apply_naming_series(frm);
        }
    },
    company: function (frm) {
        apply_naming_series(frm);
    }
});

function apply_naming_series(frm) {
    const mapping = {
        "Premier Print": "ПП-.#######",
        "Полиграфия": "П-.########",
        "Реклама": "Р-.#######",
        "Сувенир": "С-.#######"
    };

    if (frm.doc.company && mapping[frm.doc.company]) {
        console.log("Applying Naming Series for:", frm.doc.company, "->", mapping[frm.doc.company]);
        frm.set_value('naming_series', mapping[frm.doc.company]);
        // frappe.msgprint msg removed as per user request to avoid distraction
    }
}