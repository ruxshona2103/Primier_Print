import frappe
import json
import time

def reset_purchase_naming():
    ps = frappe.get_all('Property Setter', filters={'doc_type': ['in', ['Purchase Order','Purchase Invoice','Purchase Receipt']], 'property': 'options'}, fields=['name','doc_type','property','value'])
    path = '/home/gulinur/frappe-bench/backups/premierprint_property_setters_{}.json'.format(time.strftime('%Y%m%d%H%M%S'))
    with open(path, 'w') as f:
        f.write(json.dumps(ps, indent=2))
    print('backup_saved', path)
    for r in ps:
        try:
            frappe.delete_doc('Property Setter', r['name'], force=True)
            print('deleted', r['name'])
        except Exception as e:
            print('failed', r['name'], str(e))
    return ps


def cleanup_cyrillic_options():
    """Find and delete Property Setter rows where the options value contains Cyrillic letters."""
    # Find property setters with Cyrillic chars in value (Р, П, С are common)
    ps = frappe.db.sql("""
        SELECT name, doc_type, property, value
        FROM `tabProperty Setter`
        WHERE property = 'options' AND (
            value LIKE '%%Р%%' OR value LIKE '%%П%%' OR value LIKE '%%С%%'
        )
    """, as_dict=True)
    if not ps:
        print('no_cyrillic_property_setters_found')
        return []

    path = '/home/gulinur/frappe-bench/backups/premierprint_property_setters_cyrillic_{}.json'.format(time.strftime('%Y%m%d%H%M%S'))
    with open(path, 'w') as f:
        f.write(json.dumps(ps, indent=2))
    print('backup_saved', path)

    deleted = []
    for r in ps:
        try:
            frappe.delete_doc('Property Setter', r['name'], force=True)
            print('deleted', r['name'])
            deleted.append(r)
        except Exception as e:
            print('failed', r['name'], str(e))

    return deleted


def delete_named_property_setters(names):
    """Delete Property Setter rows by exact name. Returns list of deleted and not_found."""
    results = {'deleted': [], 'not_found': []}
    for n in names:
        if frappe.db.exists('Property Setter', n):
            try:
                frappe.delete_doc('Property Setter', n, force=True)
                results['deleted'].append(n)
                print('deleted', n)
            except Exception as e:
                print('failed', n, str(e))
        else:
            results['not_found'].append(n)
            print('not_found', n)
    return results


def update_named_property_setters(mapping):
    """Update Property Setter 'value' for given name->value mapping."""
    updated = []
    for name, val in mapping.items():
        if frappe.db.exists('Property Setter', name):
            frappe.db.set_value('Property Setter', name, 'value', val)
            print('updated', name, '->', val)
            updated.append(name)
        else:
            print('not_found', name)
    return updated


def inspect_property_setter(name):
    if frappe.db.exists('Property Setter', name):
        d = frappe.get_doc('Property Setter', name)
        print('name:', d.name)
        print('doc_type:', d.doc_type)
        print('property:', d.property)
        print('value_repr:', repr(d.value))
        print('modified:', d.modified)
        return d.as_dict()
    else:
        print('not_found', name)
        return None


def delete_and_verify(name):
    if frappe.db.exists('Property Setter', name):
        frappe.delete_doc('Property Setter', name, force=True)
        print('deleted', name)
    else:
        print('not_found', name)

    # Verify
    if frappe.db.exists('Property Setter', name):
        print('still_exists', name)
        return False
    else:
        print('confirmed_deleted', name)
        return True


def test_create_po():
    s = frappe.get_all('Supplier', limit=1)[0]['name']
    it = frappe.get_all('Item', limit=1)[0]['name']
    c = frappe.get_all('Company', limit=1)[0]['name']
    po = frappe.new_doc('Purchase Order')
    po.supplier = s
    po.company = c
    po.append('items', {'item_code': it, 'qty': 1})
    po.insert(ignore_permissions=True)
    name = po.name
    # cleanup
    frappe.delete_doc('Purchase Order', name, force=True)
    print('test_po_created_and_deleted', name)
    return name


def get_naming_defaults():
    from frappe.model.naming import get_default_naming_series
    return {
        'Purchase Order': get_default_naming_series('Purchase Order'),
        'Purchase Invoice': get_default_naming_series('Purchase Invoice'),
        'Purchase Receipt': get_default_naming_series('Purchase Receipt'),
    }
