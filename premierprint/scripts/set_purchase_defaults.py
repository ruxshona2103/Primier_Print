import frappe

def set_default_naming_series():
    defaults = {
        'Purchase Order': 'PO-',
        'Purchase Invoice': 'PI-',
        'Purchase Receipt': 'PR-',
    }
    for dt, val in defaults.items():
        existing = frappe.get_all('Property Setter', filters={'doc_type': dt, 'field_name': 'naming_series', 'property': 'default'}, fields=['name'])
        if existing:
            frappe.db.set_value('Property Setter', existing[0]['name'], 'value', val)
            print('updated', existing[0]['name'])
        else:
            ps = frappe.get_doc({'doctype': 'Property Setter', 'doc_type': dt, 'doctype_or_field': 'DocField', 'field_name': 'naming_series', 'property': 'default', 'property_type': 'Data', 'value': val})
            ps.insert(ignore_permissions=True)
            print('created', ps.name)
    frappe.db.commit()
    return True
