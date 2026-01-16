"""
Fixtures Sync Script - Property setterlarni to'liq sinxronlash
Yangi yozuvlarni qo'shadi, keraksizlarni o'chiradi

Usage: bench --site [site-name] execute premierprint.utils.sync_fixtures.execute
"""
import frappe

# ============================================================================
# O'CHIRILADIGAN PROPERTY SETTERLAR (hidden=1 larni bazadan o'chirish)
# Item, Customer, Supplier uchun hamma hidden maydonlar ko'rinadigan bo'ladi
# ============================================================================
HIDDEN_PROPERTY_SETTERS_TO_DELETE = [
    # Item hidden fields
    "Item-inventory_section-hidden",
    "Item-accounting-hidden",
    "Item-purchasing_tab-hidden",
    "Item-sales_details-hidden",
    "Item-item_tax_section_break-hidden",
    "Item-quality_tab-hidden",
    "Item-auto_create_assets-hidden",
    "Item-is_grouped_asset-hidden",
    "Item-over_delivery_receipt_allowance-hidden",
    "Item-over_billing_allowance-hidden",
    "Item-image-hidden",
    "Item-item_group-hidden",
    "Item-has_variants-hidden",
    "Item-standard_rate-hidden",
    "Item-brand-hidden",
    "Item-uoms-hidden",
    "Item-dashboard_tab-hidden",
    "Item-variants_section-hidden",
    "Item-asset_category-hidden",
    "Item-asset_naming_series-hidden",
    "Item-valuation_rate-hidden",
    "Item-is_fixed_asset-hidden",
    "Item-description-hidden",
    
    # Customer hidden fields
    "Customer-naming_series-hidden",
    "Customer-salutation-hidden",
    "Customer-auto_repeat_detail-hidden",
    "Customer-territory-hidden",
    "Customer-sales_team-hidden",
    "Customer-account_manager-hidden",
    "Customer-default_currency-hidden",
    "Customer-default_bank_account-hidden",
    "Customer-default_price_list-hidden",
    "Customer-internal_customer-hidden",
    "Customer-companies-hidden",
    "Customer-default_company-hidden",
    "Customer-lead_name-hidden",
    "Customer-opportunity_name-hidden",
    "Customer-prospect_name-hidden",
    "Customer-custom_auto_debit-hidden",
    
    # Supplier hidden fields
    "Supplier-is_transporter-hidden",
    "Supplier-default_bank_account-hidden",
    "Supplier-image-hidden",
    "Supplier-tax_id-hidden",
    "Supplier-country-hidden",
    "Supplier-on_hold-hidden",
    "Supplier-website-hidden",
    "Supplier-disabled-hidden",
    "Supplier-email_id-hidden",
    "Supplier-language-hidden",
    "Supplier-warn_pos-hidden",
    "Supplier-hold_type-hidden",
    "Supplier-mobile_no-hidden",
    "Supplier-warn_rfqs-hidden",
    "Supplier-prevent_pos-hidden",
    "Supplier-prevent_rfqs-hidden",
    "Supplier-release_date-hidden",
    "Supplier-tax_category-hidden",
    "Supplier-billing_address-hidden",
    "Supplier-primary_address-hidden",
    "Supplier-default_currency-hidden",
    "Supplier-shipping_address-hidden",
    "Supplier-default_price_list-hidden",
    "Supplier-supplier_primary_contact-hidden",
    "Supplier-allow_purchase_invoice_creation_without_purchase_order-hidden",
    "Supplier-allow_purchase_invoice_creation_without_purchase_receipt-hidden",
    "Supplier-supplier_type-hidden",
]

# ============================================================================
# O'CHIRILADIGAN CUSTOM FIELDLAR
# ============================================================================
CUSTOM_FIELDS_TO_DELETE = [
    "Customer-custom_telefon",
    "Customer-custom_pasport_seriyasi",
    "Customer-telefon",
    "Customer-pasport_seriyasi",
    "Payment Entry-custom_expense_category",
    "Payment Entry-expense_category",
]

# ============================================================================
# QO'SHILADIGAN PROPERTY SETTERLAR (Item, Customer, Supplier uchun)
# Bu yerda sizning property_setter.json dagi sozlamalar
# ============================================================================
PROPERTY_SETTERS_TO_CREATE = [
    # ==================== CUSTOMER ====================
    {"doc_type": "Customer", "field_name": "image", "property": "hidden", "value": "0", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "customer_type", "property": "default", "value": "Individual", "property_type": "Text"},
    {"doc_type": "Customer", "field_name": "customer_type", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "customer_group", "property": "hidden", "value": "0", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "customer_group", "property": "reqd", "value": "1", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "customer_group", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "customer_group", "property": "in_list_view", "value": "0", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "naming_series", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "naming_series", "property": "options", "value": "\n00000", "property_type": "Text"},
    {"doc_type": "Customer", "field_name": "naming_series", "property": "default", "value": "", "property_type": "Text"},
    {"doc_type": "Customer", "field_name": "passport_nusxa", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "mijoz_rasmi", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    {"doc_type": "Customer", "field_name": "primary_address_and_contact_detail", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    
    # ==================== ITEM ====================
    {"doc_type": "Item", "field_name": "naming_series", "property": "print_hide", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "naming_series", "property": "report_hide", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "naming_series", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "naming_series", "property": "options", "value": "ITEM-.####", "property_type": "Text"},
    {"doc_type": "Item", "field_name": "naming_series", "property": "default", "value": "ITEM-.####", "property_type": "Text"},
    {"doc_type": "Item", "field_name": "item_code", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "item_name", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "item_name", "property": "in_list_view", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "item_name", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "item_group", "property": "reqd", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "item_group", "property": "default", "value": "Mahsulotlar", "property_type": "Text"},
    {"doc_type": "Item", "field_name": "stock_uom", "property": "default", "value": "Dona", "property_type": "Text"},
    {"doc_type": "Item", "field_name": "description", "property": "print_hide", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "field_name": "description", "property": "report_hide", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "doctype_or_field": "DocType", "field_name": None, "property": "show_title_field_in_link", "value": "1", "property_type": "Check"},
    {"doc_type": "Item", "doctype_or_field": "DocType", "field_name": None, "property": "autoname", "value": "naming_series:", "property_type": "Data"},
    
    # ==================== SUPPLIER ====================
    {"doc_type": "Supplier", "field_name": "supplier_group", "property": "allow_in_quick_entry", "value": "1", "property_type": "Check"},
    {"doc_type": "Supplier", "field_name": "supplier_group", "property": "reqd", "value": "1", "property_type": "Check"},
    {"doc_type": "Supplier", "field_name": "naming_series", "property": "options", "value": "SUP-.YYYY.-", "property_type": "Text"},
    {"doc_type": "Supplier", "field_name": "naming_series", "property": "reqd", "value": "0", "property_type": "Check"},
    {"doc_type": "Supplier", "doctype_or_field": "DocType", "field_name": None, "property": "search_fields", "value": "supplier_group", "property_type": "Data"},
]


def execute():
    """Asosiy funksiya - barcha sinxronlashni bajaradi"""
    print("\n" + "="*70)
    print("🔄 FIXTURES SYNC - Property Setterlar va Custom Fieldlarni sinxronlash")
    print("="*70)
    
    deleted_ps = 0
    deleted_cf = 0
    created_ps = 0
    updated_ps = 0
    
    # 1. HIDDEN Property Setterlarni o'chirish
    print("\n📋 [1/3] Hidden Property Setterlarni o'chirish...")
    for name in HIDDEN_PROPERTY_SETTERS_TO_DELETE:
        if frappe.db.exists("Property Setter", name):
            frappe.delete_doc("Property Setter", name, force=True)
            print(f"   🗑️  O'chirildi: {name}")
            deleted_ps += 1
    
    # 2. Custom Fieldlarni o'chirish
    print("\n📋 [2/3] Keraksiz Custom Fieldlarni o'chirish...")
    for name in CUSTOM_FIELDS_TO_DELETE:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, force=True)
            print(f"   🗑️  O'chirildi: {name}")
            deleted_cf += 1
    
    # 3. Property Setterlarni yaratish/yangilash
    print("\n📋 [3/3] Property Setterlarni yaratish/yangilash...")
    for ps in PROPERTY_SETTERS_TO_CREATE:
        doc_type = ps.get("doc_type")
        field_name = ps.get("field_name")
        prop = ps.get("property")
        doctype_or_field = ps.get("doctype_or_field", "DocField")
        
        # Property Setter nomi
        if field_name:
            ps_name = f"{doc_type}-{field_name}-{prop}"
        else:
            ps_name = f"{doc_type}-main-{prop}"
        
        if frappe.db.exists("Property Setter", ps_name):
            # Mavjudini yangilash
            doc = frappe.get_doc("Property Setter", ps_name)
            doc.value = ps.get("value")
            doc.save()
            print(f"   ✏️  Yangilandi: {ps_name}")
            updated_ps += 1
        else:
            # Yangi yaratish
            doc = frappe.new_doc("Property Setter")
            doc.doctype_or_field = doctype_or_field
            doc.doc_type = doc_type
            doc.field_name = field_name
            doc.property = prop
            doc.value = ps.get("value")
            doc.property_type = ps.get("property_type")
            doc.insert()
            print(f"   ✅ Yaratildi: {ps_name}")
            created_ps += 1
    
    frappe.db.commit()
    
    print("\n" + "="*70)
    print("✅ YAKUNLANDI!")
    print(f"   - Hidden Property Setter o'chirildi: {deleted_ps} ta")
    print(f"   - Custom Field o'chirildi: {deleted_cf} ta")
    print(f"   - Property Setter yaratildi: {created_ps} ta")
    print(f"   - Property Setter yangilandi: {updated_ps} ta")
    print("="*70)
    print("\n💡 Endi 'bench clear-cache' va brauzer refresh qiling!")
    
    return {
        "deleted_property_setters": deleted_ps,
        "deleted_custom_fields": deleted_cf,
        "created_property_setters": created_ps,
        "updated_property_setters": updated_ps
    }
