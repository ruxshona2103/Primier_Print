# -*- coding: utf-8 -*-
# Copyright (c) 2026, Premier Print
# Surgical Cleanup Script - fixtures va bazani tozalash uchun

import json
import os
import frappe

# ===================== SOZLAMALAR =====================

# Fixtures papka yo'li (skript joylashgan joyga nisbatan)
FIXTURES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "fixtures"
)

# O'chiriladigan Client Script nomlari
CLIENT_SCRIPTS_TO_REMOVE = [
    "Stock entry avtomatik id",
    "Stock Entry - Premier Print Transfer Logic",
    "Stock Entry - Optimized Logic",
    "Stock Entry - Custom Logic",
    "stock entry - add item",
    "Stock Entry - hide options",
    "Purchase Order",
    "Payment Entry - Expenses Support",
]

# O'chiriladigan Custom Field nomlari
CUSTOM_FIELDS_TO_REMOVE = [
    "Payment Entry-expense_category",
    "Payment Entry-custom_expense_category",
]

# O'chiriladigan Property Setter nomlari (Payment Entry party_type uchun)
PROPERTY_SETTERS_TO_REMOVE = [
    "Payment Entry-party_type-options",
    "Payment Entry-main-party_type-options",
]


# ===================== YORDAMCHI FUNKSIYALAR =====================

def load_json_file(filepath):
    """JSON faylni o'qib, Python list/dict qaytaradi."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"⚠️  Fayl topilmadi: {filepath}")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ JSON xatosi {filepath}: {e}")
        return None


def save_json_file(filepath, data):
    """Ma'lumotni JSON faylga chiroyli formatda yozadi."""
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
        print(f"✅ Fayl saqlandi: {filepath}")
        return True
    except Exception as e:
        print(f"❌ Faylni saqlashda xato {filepath}: {e}")
        return False


def filter_json_by_names(data, names_to_remove, name_field="name"):
    """
    JSON ro'yxatidan berilgan nomlarni filtrlab tashlab,
    tozalangan ro'yxat va o'chirilganlar sonini qaytaradi.
    """
    if not isinstance(data, list):
        print("⚠️  Ma'lumot list emas, o'tkazib yuborildi")
        return data, 0

    original_count = len(data)
    filtered_data = [
        item for item in data
        if item.get(name_field) not in names_to_remove
    ]
    removed_count = original_count - len(filtered_data)
    
    return filtered_data, removed_count


# ===================== JSON TOZALASH =====================

def clean_client_scripts():
    """client_script.json faylini tozalaydi."""
    print("\n📄 Client Script faylini tozalash...")
    filepath = os.path.join(FIXTURES_PATH, "client_script.json")
    
    data = load_json_file(filepath)
    if data is None:
        return
    
    cleaned_data, removed_count = filter_json_by_names(
        data, CLIENT_SCRIPTS_TO_REMOVE
    )
    
    if removed_count > 0:
        save_json_file(filepath, cleaned_data)
        print(f"   🗑️  {removed_count} ta client script o'chirildi")
    else:
        print("   ℹ️  O'chiriladigan client script topilmadi")


def clean_custom_fields():
    """custom_field.json faylini tozalaydi."""
    print("\n📄 Custom Field faylini tozalash...")
    filepath = os.path.join(FIXTURES_PATH, "custom_field.json")
    
    data = load_json_file(filepath)
    if data is None:
        return
    
    cleaned_data, removed_count = filter_json_by_names(
        data, CUSTOM_FIELDS_TO_REMOVE
    )
    
    if removed_count > 0:
        save_json_file(filepath, cleaned_data)
        print(f"   🗑️  {removed_count} ta custom field o'chirildi")
    else:
        print("   ℹ️  O'chiriladigan custom field topilmadi")


def clean_property_setters():
    """property_setter.json faylini tozalaydi."""
    print("\n📄 Property Setter faylini tozalash...")
    filepath = os.path.join(FIXTURES_PATH, "property_setter.json")
    
    data = load_json_file(filepath)
    if data is None:
        return
    
    cleaned_data, removed_count = filter_json_by_names(
        data, PROPERTY_SETTERS_TO_REMOVE
    )
    
    if removed_count > 0:
        save_json_file(filepath, cleaned_data)
        print(f"   🗑️  {removed_count} ta property setter o'chirildi")
    else:
        print("   ℹ️  O'chiriladigan property setter topilmadi")


# ===================== BAZADAN O'CHIRISH =====================

def delete_from_database():
    """Bazadan eski/keraksiz hujjatlarni o'chiradi."""
    print("\n🗄️  Bazadan o'chirish...")
    
    # Client Script larni o'chirish
    for script_name in CLIENT_SCRIPTS_TO_REMOVE:
        try:
            if frappe.db.exists("Client Script", script_name):
                frappe.delete_doc("Client Script", script_name, force=True)
                print(f"   ✅ Client Script o'chirildi: {script_name}")
            else:
                print(f"   ℹ️  Bazada yo'q: Client Script '{script_name}'")
        except Exception as e:
            print(f"   ❌ Xato: Client Script '{script_name}': {e}")
    
    # Custom Field larni o'chirish
    for field_name in CUSTOM_FIELDS_TO_REMOVE:
        try:
            if frappe.db.exists("Custom Field", field_name):
                frappe.delete_doc("Custom Field", field_name, force=True)
                print(f"   ✅ Custom Field o'chirildi: {field_name}")
            else:
                print(f"   ℹ️  Bazada yo'q: Custom Field '{field_name}'")
        except Exception as e:
            print(f"   ❌ Xato: Custom Field '{field_name}': {e}")
    
    # Property Setter larni o'chirish
    for setter_name in PROPERTY_SETTERS_TO_REMOVE:
        try:
            if frappe.db.exists("Property Setter", setter_name):
                frappe.delete_doc("Property Setter", setter_name, force=True)
                print(f"   ✅ Property Setter o'chirildi: {setter_name}")
            else:
                print(f"   ℹ️  Bazada yo'q: Property Setter '{setter_name}'")
        except Exception as e:
            print(f"   ❌ Xato: Property Setter '{setter_name}': {e}")
    
    # O'zgarishlarni saqlash
    frappe.db.commit()
    print("\n   💾 Baza o'zgarishlari saqlandi")


# ===================== ASOSIY FUNKSIYA =====================

def run_cleanup(include_database=True):
    """
    Asosiy tozalash funksiyasi.
    
    Args:
        include_database: True bo'lsa, bazadan ham o'chiradi
    """
    print("=" * 60)
    print("🧹 SURGICAL CLEANUP - Premier Print")
    print("=" * 60)
    
    # 1. JSON fayllarni tozalash
    print("\n📁 FIXTURES FAYLLARNI TOZALASH")
    print("-" * 40)
    clean_client_scripts()
    clean_custom_fields()
    clean_property_setters()
    
    # 2. Bazadan o'chirish
    if include_database:
        print("\n" + "-" * 40)
        delete_from_database()
    
    print("\n" + "=" * 60)
    print("✅ TOZALASH YAKUNLANDI!")
    print("=" * 60)


# ===================== CLI INTERFEYS =====================

def execute():
    """bench execute orqali ishga tushirish uchun."""
    run_cleanup(include_database=True)


def execute_json_only():
    """Faqat JSON fayllarni tozalash (bazaga tegmasdan)."""
    run_cleanup(include_database=False)


if __name__ == "__main__":
    # Agar to'g'ridan-to'g'ri python orqali ishga tushirilsa
    print("⚠️  Bu skriptni bench execute orqali ishga tushiring:")
    print("   bench execute premierprint.utils.surgical_cleanup.execute")
