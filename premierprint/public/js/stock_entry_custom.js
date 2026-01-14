frappe.ui.form.on('Stock Entry', {
    onload: function(frm) {
        if (frm.is_new()) {
            set_stock_naming_series(frm);
        }
    },
    refresh: function(frm) {
        if (frm.is_new()) {
            set_stock_naming_series(frm);
        }
    },
    company: function(frm) {
        set_stock_naming_series(frm);
    }
});

function set_stock_naming_series(frm) {
    if (frm.doc.company) {
        let target_series = "";

        if (frm.doc.company == "Premier Print") {
            target_series = "ПП-#######";
        } else if (frm.doc.company == "Полиграфия") {
            target_series = "П-#######";
        } else if (frm.doc.company == "Сувенир") {
            target_series = "С-#######";
        } else if (frm.doc.company == "Реклама") {
            target_series = "Р-#######";
        }

        if (target_series && frm.doc.naming_series !== target_series) {
            frm.set_value("naming_series", target_series);
        }
    }
}
