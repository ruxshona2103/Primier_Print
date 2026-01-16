"""
Fixtures Sync Script - O'chirilgan property setterlarni bazadan ham o'chiradi
Usage: bench --site [site-name] execute premierprint.utils.sync_fixtures.execute
"""
import frappe

# O'chiriladigan property setterlar ro'yxati
PROPERTY_SETTERS_TO_DELETE = [
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

# O'chiriladigan custom fieldlar (agar bo'lsa)
CUSTOM_FIELDS_TO_DELETE = [
    "Customer-custom_telefon",
    "Customer-custom_pasport_seriyasi",
    "Customer-telefon",
    "Customer-pasport_seriyasi",
    "Payment Entry-custom_expense_category",
    "Payment Entry-expense_category",
]

def execute():
    """Asosiy funksiya - barcha tozalashlarni bajaradi"""
    print("\n" + "="*60)
    print("🔄 FIXTURES SYNC - Property Setterlar va Custom Fieldlarni tozalash")
    print("="*60)
    
    deleted_ps = 0
    deleted_cf = 0
    
    # Property Setterlarni o'chirish
    print("\n📋 Property Setterlarni tekshirish...")
    for name in PROPERTY_SETTERS_TO_DELETE:
        if frappe.db.exists("Property Setter", name):
            frappe.delete_doc("Property Setter", name, force=True)
            print(f"   ✅ O'chirildi: {name}")
            deleted_ps += 1
    
    # Custom Fieldlarni o'chirish
    print("\n📋 Custom Fieldlarni tekshirish...")
    for name in CUSTOM_FIELDS_TO_DELETE:
        if frappe.db.exists("Custom Field", name):
            frappe.delete_doc("Custom Field", name, force=True)
            print(f"   ✅ O'chirildi: {name}")
            deleted_cf += 1
    
    frappe.db.commit()
    
    print("\n" + "="*60)
    print(f"✅ YAKUNLANDI!")
    print(f"   - Property Setter o'chirildi: {deleted_ps} ta")
    print(f"   - Custom Field o'chirildi: {deleted_cf} ta")
    print("="*60)
    print("\n💡 Endi 'bench clear-cache' buyrug'ini bajaring!")
    
    return {"deleted_property_setters": deleted_ps, "deleted_custom_fields": deleted_cf}
