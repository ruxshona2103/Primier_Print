import frappe
from frappe import _


def on_submit(doc, method):
    """Purchase Receipt submit bo'lganda Purchase Invoice avtomatik yaratish va submit qilish.
    
    Faqat internal supplier (ichki taminotchi) uchun ishlaydi.
    """
    # Faqat internal supplier uchun
    if not doc.is_internal_supplier:
        return
    
    # Agar allaqachon Purchase Invoice mavjud bo'lsa, yaratmaymiz
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
    
    # Purchase Invoice yaratish
    pi = frappe.new_doc("Purchase Invoice")
    pi.supplier = doc.supplier
    pi.company = doc.company
    pi.posting_date = doc.posting_date
    pi.currency = doc.currency
    pi.conversion_rate = doc.conversion_rate
    pi.buying_price_list = doc.buying_price_list
    pi.is_internal_supplier = doc.is_internal_supplier
    pi.represents_company = doc.represents_company
    pi.bill_no = doc.name  # Reference to Purchase Receipt
    pi.update_stock = 0  # Stock already updated by Purchase Receipt
    
    # Items qo'shish
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
            "pr_detail": item.name
        })
    
    # Taxes qo'shish (agar mavjud bo'lsa)
    for tax in doc.get("taxes", []):
        pi.append("taxes", {
            "charge_type": tax.charge_type,
            "account_head": tax.account_head,
            "description": tax.description,
            "rate": tax.rate,
            "tax_amount": tax.tax_amount,
            "cost_center": tax.cost_center
        })
    
    pi.flags.ignore_permissions = True
    pi.insert()
    pi.submit()
    
    frappe.msgprint(
        _("Purchase Invoice <a href='/app/purchase-invoice/{0}'>{0}</a> created and submitted").format(pi.name),
        indicator="green",
        alert=True
    )
    
    # Comment qo'shish
    doc.add_comment("Info", _("Purchase Invoice {0} created and submitted").format(
        f'<a href="/app/purchase-invoice/{pi.name}">{pi.name}</a>'
    ))
