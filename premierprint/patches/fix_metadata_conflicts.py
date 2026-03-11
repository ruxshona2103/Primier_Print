import frappe


PREMIERPRINT_MODULE = "premierprint"

PURCHASE_INVOICE_ITEM_FIELD_DEFS = {
    "custom_finished_good": {
        "label": "Finished Good",
        "fieldtype": "Link",
        "options": "Item",
        "insert_after": "page_break",
    },
    "custom_sales_order": {
        "label": "Sales Order",
        "fieldtype": "Link",
        "options": "Sales Order",
        "insert_after": "custom_finished_good",
    },
    "custom_sales_order_item": {
        "label": "Sales Order Item",
        "fieldtype": "Data",
        "insert_after": "custom_sales_order",
    },
}

MODULE_OWNED_FIELDS = {
    "Purchase Invoice Item": [
        "custom_finished_good",
        "custom_sales_order",
        "custom_sales_order_item",
    ],
    "Stock Entry": ["custom_sales_order"],
    "Stock Entry Detail": ["custom_sales_order"],
}


def _pluck_names(dt, fieldname):
    rows = frappe.db.sql(
        """
        SELECT name
        FROM `tabCustom Field`
        WHERE dt = %s AND fieldname = %s
        ORDER BY modified DESC, creation DESC, name DESC
        """,
        (dt, fieldname),
        as_dict=True,
    )
    return [row.name for row in rows]


def _delete_custom_field_rows(dt, fieldname):
    names = _pluck_names(dt, fieldname)
    if not names:
        return []

    frappe.db.sql(
        "DELETE FROM `tabCustom Field` WHERE dt = %s AND fieldname = %s",
        (dt, fieldname),
    )
    return names


def _has_column(table_name, column_name):
    return bool(
        frappe.db.sql(
            """
            SELECT 1
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = %s
              AND COLUMN_NAME = %s
            LIMIT 1
            """,
            (table_name, column_name),
        )
    )


def _upsert_purchase_invoice_item_field(fieldname):
    definition = PURCHASE_INVOICE_ITEM_FIELD_DEFS[fieldname]
    field_name = f"Purchase Invoice Item-{fieldname}"
    custom_field = frappe.db.get_value("Custom Field", field_name)

    values = {
        "dt": "Purchase Invoice Item",
        "fieldname": fieldname,
        "module": PREMIERPRINT_MODULE,
        "label": definition["label"],
        "fieldtype": definition["fieldtype"],
        "options": definition.get("options"),
        "insert_after": definition["insert_after"],
        "hidden": 0,
        "read_only": 0,
        "no_copy": 0,
        "reqd": 0,
        "in_list_view": 0,
        "in_standard_filter": 0,
    }

    if custom_field:
        doc = frappe.get_doc("Custom Field", field_name)
        doc.update(values)
        doc.save(ignore_permissions=True)
        return doc.name

    doc = frappe.get_doc({
        "doctype": "Custom Field",
        "name": field_name,
        **values,
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _normalize_module_assignments():
    for dt, fieldnames in MODULE_OWNED_FIELDS.items():
        for fieldname in fieldnames:
            frappe.db.sql(
                """
                UPDATE `tabCustom Field`
                SET module = %s
                WHERE dt = %s AND fieldname = %s
                  AND (module IS NULL OR module = '' OR module != %s)
                """,
                (PREMIERPRINT_MODULE, dt, fieldname, PREMIERPRINT_MODULE),
            )


def execute():
    deleted_purchase_invoice_item = _delete_custom_field_rows(
        "Purchase Invoice Item", "custom_sales_order"
    )
    deleted_payment_entry = _delete_custom_field_rows(
        "Payment Entry", "custom_expense_category"
    )

    if not _has_column("tabPurchase Invoice Item", "custom_sales_order"):
        frappe.throw("tabPurchase Invoice Item.custom_sales_order column not found")

    recreated_field = _upsert_purchase_invoice_item_field("custom_sales_order")

    if frappe.db.exists("Custom Field", "Purchase Invoice Item-custom_finished_good"):
        _upsert_purchase_invoice_item_field("custom_finished_good")

    if frappe.db.exists("Custom Field", "Purchase Invoice Item-custom_sales_order_item"):
        _upsert_purchase_invoice_item_field("custom_sales_order_item")

    _normalize_module_assignments()
    frappe.clear_cache(doctype="Purchase Invoice Item")
    frappe.clear_cache(doctype="Payment Entry")
    frappe.db.commit()

    print(
        {
            "deleted_purchase_invoice_item_rows": deleted_purchase_invoice_item,
            "deleted_payment_entry_rows": deleted_payment_entry,
            "recreated_purchase_invoice_item_row": recreated_field,
        }
    )
