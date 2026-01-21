"""
Inter-Company Purchase Invoice Creation Module.

Sales Invoice submit qilinganda, agar mijoz ichki kompaniya bo'lsa,
avtomatik Purchase Invoice yaratadi.

Author: PremierPrint
Version: 1.0.0
"""

import frappe
from frappe import _

# Module uchun logger
logger = frappe.logger("inter_company", allow_site=True, file_count=5)


def create_inter_company_purchase_invoice(doc, method):
    """
    Sales Invoice on_submit eventida Purchase Invoice yaratish.
    
    Bu funksiya Sales Invoice submit qilinganda avtomatik chaqiriladi.
    Agar mijoz internal customer bo'lsa, tegishli kompaniya uchun
    Purchase Invoice yaratiladi.
    
    Args:
        doc: Sales Invoice document
        method: Hook method nomi (on_submit)
    
    Returns:
        None
    
    Raises:
        frappe.ValidationError: Agar Purchase Invoice yaratishda xatolik bo'lsa
    """
    logger.debug(f"[START] Inter-company PI creation for {doc.name}")
    
    # 1. Internal customer tekshiruvi
    if not doc.is_internal_customer:
        logger.debug(f"[SKIP] {doc.name} - not an internal customer")
        return
    
    # 2. Duplicate tekshiruvi - Purchase Invoice allaqachon yaratilganmi
    if _is_inter_company_pi_exists(doc.name):
        logger.info(f"[SKIP] {doc.name} - Purchase Invoice already exists")
        frappe.msgprint(
            _("Purchase Invoice allaqachon yaratilgan"),
            indicator="orange",
            alert=True
        )
        return
    
    try:
        # 3. ERPNext funksiyasidan foydalanib Purchase Invoice yaratish
        from erpnext.accounts.doctype.sales_invoice.sales_invoice import (
            make_inter_company_purchase_invoice
        )
        
        logger.debug(f"[PROCESS] Creating Purchase Invoice for {doc.name}")
        
        # Purchase Invoice object yaratish
        purchase_invoice = make_inter_company_purchase_invoice(doc.name)
        
        # Saqlash (permissions tekshirmasdan)
        purchase_invoice.insert(ignore_permissions=True)
        
        logger.info(f"[SUCCESS] Created Purchase Invoice {purchase_invoice.name} from {doc.name}")
        
        # 4. Foydalanuvchiga xabar berish
        _notify_success(doc.name, purchase_invoice.name)
        
    except Exception as e:
        # Xatolikni log qilish
        logger.error(f"[FAIL] Error creating PI for {doc.name}: {str(e)}")
        
        # Error log yaratish (admin uchun)
        frappe.log_error(
            title=f"Inter-Company PI Creation Failed: {doc.name}",
            message=frappe.get_traceback()
        )
        
        # Foydalanuvchiga tushunarli xabar
        frappe.throw(
            _("Purchase Invoice yaratishda xatolik yuz berdi: {0}").format(str(e)),
            title=_("Inter-Company Transaction Error")
        )


def _is_inter_company_pi_exists(sales_invoice_name):
    """
    Purchase Invoice allaqachon yaratilganligini tekshirish.
    
    ERPNext inter-company tranzaksiyalarida Purchase Invoice
    `inter_company_invoice_reference` fieldida Sales Invoice nomini saqlaydi.
    
    Args:
        sales_invoice_name: Sales Invoice nomi
        
    Returns:
        bool: True agar Purchase Invoice allaqachon mavjud bo'lsa
    """
    return frappe.db.exists(
        "Purchase Invoice",
        {"inter_company_invoice_reference": sales_invoice_name}
    )


def _notify_success(si_name, pi_name):
    """
    Muvaffaqiyat haqida foydalanuvchiga xabar berish.
    
    Args:
        si_name: Sales Invoice nomi
        pi_name: Yaratilgan Purchase Invoice nomi
    """
    # UI alert (hozirgi sahifada) - link bilan
    frappe.msgprint(
        msg=_("Inter-Company Purchase Invoice yaratildi: <a href='/app/purchase-invoice/{0}'><b>{0}</b></a>").format(pi_name),
        title=_("Muvaffaqiyatli"),
        indicator="green",
        alert=True
    )