
frappe.ui.form.on('Item', {
    refresh: function (frm) {
        // Hide naming_series field as requested by user
        frm.set_df_property('naming_series', 'hidden', 1);

        // Clear value if set (to avoid confusion)
        if (frm.doc.naming_series) {
            frm.set_value('naming_series', '');
        }
    }
});

