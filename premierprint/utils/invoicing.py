"""
Inter-Company Invoicing Automation Module.

Handles automatic document creation for internal party transactions:
- DN → SI: Delivery Note submit → Sales Invoice (for internal customers)
- PR → PI: Purchase Receipt submit → Purchase Invoice (for internal suppliers)
- PI → SI: Purchase Invoice submit → Ensure linked Sales Invoice is submitted

Author: PremierPrint
"""

import frappe
from frappe import _


def on_delivery_note_submit(doc, method):
    """Delivery Note submit bo'lganda Sales Invoice avtomatik yaratish.

    Faqat internal customer (ichki mijoz) uchun ishlaydi.
    DN submit → SI create & submit (update_stock=0).
    """
    if not doc.customer:
        return

    is_internal = frappe.db.get_value("Customer", doc.customer, "is_internal_customer")
    if not is_internal:
        return

    # Duplicate tekshiruvi
    existing_si = frappe.db.exists("Sales Invoice", {
        "docstatus": ["<", 2],
        "return_against": ["is", "not set"],
        "custom_delivery_note_ref": doc.name
    })
    if not existing_si:
        # Fallback: remarks orqali tekshirish
        existing_si = frappe.db.exists("Sales Invoice", {
            "docstatus": ["<", 2],
            "remarks": ["like", f"%{doc.name}%"]
        })

    if existing_si:
        frappe.msgprint(
            _("Sales Invoice {0} already exists for this Delivery Note").format(existing_si),
            indicator="orange"
        )
        return

    try:
        si = frappe.new_doc("Sales Invoice")
        si.customer = doc.customer
        si.company = doc.company
        si.posting_date = doc.posting_date
        si.currency = doc.currency
        si.selling_price_list = doc.selling_price_list
        si.is_internal_customer = 1
        si.represents_company = frappe.db.get_value("Customer", doc.customer, "represents_company")
        si.update_stock = 0  # Stock already updated by Delivery Note
        si.remarks = _("Auto-created from Delivery Note {0}").format(doc.name)

        # custom field orqali bog'lash (agar mavjud bo'lsa)
        if hasattr(si, "custom_delivery_note_ref"):
            si.custom_delivery_note_ref = doc.name

        for item in doc.items:
            si.append("items", {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "qty": item.qty,
                "uom": item.uom,
                "rate": item.rate,
                "amount": item.amount,
                "warehouse": item.warehouse,
                "delivery_note": doc.name,
                "dn_detail": item.name,
            })

        si.flags.ignore_permissions = True
        si.insert()
        si.submit()

        frappe.msgprint(
            _("Sales Invoice <a href='/app/sales-invoice/{0}'>{0}</a> auto-created and submitted").format(si.name),
            indicator="green",
            alert=True
        )

        # Cross-reference comments
        doc.add_comment("Info", _("Sales Invoice {0} auto-created").format(
            f'<a href="/app/sales-invoice/{si.name}">{si.name}</a>'
        ))
        si.add_comment("Info", _("Created from Delivery Note {0}").format(
            f'<a href="/app/delivery-note/{doc.name}">{doc.name}</a>'
        ))

    except Exception as e:
        frappe.log_error(
            title=_("DN → SI Auto-Creation Failed: {0}").format(doc.name),
            message=frappe.get_traceback()
        )
        frappe.throw(
            _("Sales Invoice yaratishda xatolik: {0}").format(str(e)),
            title=_("Inter-Company Error")
        )


def on_purchase_receipt_submit(doc, method):
    """Purchase Receipt submit bo'lganda Purchase Invoice avtomatik yaratish.

    Faqat internal supplier (ichki taminotchi) uchun ishlaydi.
    PR submit → PI create & submit (update_stock=0).
    """
    if not doc.supplier:
        return

    is_internal = frappe.db.get_value("Supplier", doc.supplier, "is_internal_supplier")
    if not is_internal:
        return

    # Duplicate tekshiruvi
    existing_pi = frappe.db.exists("Purchase Invoice", {
        "docstatus": ["<", 2],
        "bill_no": doc.name
    })

    if existing_pi:
        frappe.msgprint(
            _("Purchase Invoice {0} already exists for this Purchase Receipt").format(existing_pi),
            indicator="orange"
        )
        return

    try:
        pi = frappe.new_doc("Purchase Invoice")
        pi.supplier = doc.supplier
        pi.company = doc.company
        pi.posting_date = doc.posting_date
        pi.currency = doc.currency
        pi.conversion_rate = doc.conversion_rate
        pi.buying_price_list = doc.buying_price_list
        pi.is_internal_supplier = 1
        pi.represents_company = frappe.db.get_value("Supplier", doc.supplier, "represents_company")
        pi.bill_no = doc.name  # Reference to Purchase Receipt
        pi.update_stock = 0  # Stock already updated by Purchase Receipt

        for item in doc.items:
            pi.append("items", {
                "item_code": item.item_code,
                "item_name": item.item_name,
                "description": item.description,
                "qty": item.qty,
                "uom": item.uom,
                "stock_uom": item.stock_uom,
                "conversion_factor": item.conversion_factor,
                "rate": item.rate,
                "amount": item.amount,
                "warehouse": item.warehouse,
                "expense_account": item.expense_account,
                "cost_center": item.cost_center,
                "purchase_receipt": doc.name,
                "pr_detail": item.name,
            })

        # Taxes (agar mavjud bo'lsa)
        for tax in doc.get("taxes", []):
            pi.append("taxes", {
                "charge_type": tax.charge_type,
                "account_head": tax.account_head,
                "description": tax.description,
                "rate": tax.rate,
                "tax_amount": tax.tax_amount,
                "cost_center": tax.cost_center,
            })

        pi.flags.ignore_permissions = True
        pi.insert()
        pi.submit()

        frappe.msgprint(
            _("Purchase Invoice <a href='/app/purchase-invoice/{0}'>{0}</a> auto-created and submitted").format(pi.name),
            indicator="green",
            alert=True
        )

        # Cross-reference comments
        doc.add_comment("Info", _("Purchase Invoice {0} auto-created").format(
            f'<a href="/app/purchase-invoice/{pi.name}">{pi.name}</a>'
        ))
        pi.add_comment("Info", _("Created from Purchase Receipt {0}").format(
            f'<a href="/app/purchase-receipt/{doc.name}">{doc.name}</a>'
        ))

    except Exception as e:
        frappe.log_error(
            title=_("PR → PI Auto-Creation Failed: {0}").format(doc.name),
            message=frappe.get_traceback()
        )
        frappe.throw(
            _("Purchase Invoice yaratishda xatolik: {0}").format(str(e)),
            title=_("Inter-Company Error")
        )


def on_purchase_invoice_submit(doc, method):
    """Purchase Invoice submit bo'lganda bog'langan Sales Invoice ni ham submit qilish.

    Reverse sync: PI submit → linked SI submit (agar hali Draft bo'lsa).
    """
    if not doc.supplier:
        return

    is_internal = frappe.db.get_value("Supplier", doc.supplier, "is_internal_supplier")
    if not is_internal:
        return

    # SI ni topish: inter_company_invoice_reference orqali
    linked_si = None

    if doc.get("inter_company_invoice_reference"):
        linked_si = doc.inter_company_invoice_reference

    # Fallback: bill_no (PR name) orqali DN ni topib, undan SI ni topish
    if not linked_si and doc.bill_no:
        # bill_no = Purchase Receipt name
        # PR yaratilgan DN bilan bog'langan SI ni izlash
        linked_si = frappe.db.get_value("Sales Invoice", {
            "docstatus": 0,  # Draft
            "remarks": ["like", f"%{doc.bill_no}%"]
        }, "name")

    if not linked_si:
        return

    # SI hali Draft bo'lsa, submit qilish
    si_doc = frappe.get_doc("Sales Invoice", linked_si)
    if si_doc.docstatus == 0:
        try:
            si_doc.flags.ignore_permissions = True
            si_doc.submit()

            frappe.msgprint(
                _("Linked Sales Invoice <a href='/app/sales-invoice/{0}'>{0}</a> auto-submitted").format(si_doc.name),
                indicator="green",
                alert=True
            )

            si_doc.add_comment("Info", _("Auto-submitted via Purchase Invoice {0}").format(
                f'<a href="/app/purchase-invoice/{doc.name}">{doc.name}</a>'
            ))

        except Exception as e:
            frappe.log_error(
                title=_("PI → SI Reverse Sync Failed: {0}").format(doc.name),
                message=frappe.get_traceback()
            )
            # Don't throw - PI should still succeed even if SI sync fails
            frappe.msgprint(
                _("Sales Invoice {0} ni submit qilishda xatolik: {1}").format(linked_si, str(e)),
                indicator="orange"
            )
