"""
Auto-increment naming for Item and Customer
Cheksiz raqamlar - million, milliard va undan ko'p!
"""
import frappe

@frappe.whitelist()
def get_next_item_id():
    """
    Keyingi Item ID ni qaytaradi (API method)
    Faqat 1-5 xonali raqamlarni hisobga oladi (eski 1100002 kabi uzun raqamlar ignore)
    """
    max_id = frappe.db.sql("""
        SELECT MAX(CAST(item_code AS UNSIGNED)) as max_id
        FROM `tabItem`
        WHERE item_code REGEXP '^[0-9]{1,5}$'
    """, as_dict=True)

    next_id = 1
    if max_id and max_id[0].get('max_id'):
        next_id = int(max_id[0]['max_id']) + 1

    return str(next_id)


@frappe.whitelist()
def get_next_customer_id():
    """
    Keyingi Customer ID ni qaytaradi (API method)
    """
    max_id = frappe.db.sql("""
        SELECT MAX(CAST(name AS UNSIGNED)) as max_id
        FROM `tabCustomer`
        WHERE name REGEXP '^[0-9]+$'
    """, as_dict=True)

    next_id = 1
    if max_id and max_id[0].get('max_id'):
        next_id = int(max_id[0]['max_id']) + 1

    return str(next_id)


def autoname_item(doc, method):
    """
    Item uchun avtomatik raqam berish: 1, 2, 3, 4, ... (cheksiz)
    """
    # Yangi Item yaratilayotganini tekshirish (eski ITEM- formatidan ham tozalash)
    if not doc.item_code or doc.item_code.startswith("new-item") or doc.item_code.startswith("ITEM-"):
        next_id = get_next_item_id()
        doc.item_code = next_id

    # Name ni ham raqam qilish (eski format bo'lsa ham)
    if not doc.name or doc.name.startswith("new-item") or doc.name.startswith("ITEM-"):
        doc.name = doc.item_code
        # Item Name ga ID yozilmasin - foydalanuvchi o'zi kiritadi


def autoname_customer(doc, method):
    """
    Customer uchun avtomatik raqam berish: 1, 2, 3, 4, ... (cheksiz)
    """
    if not doc.name or doc.name.startswith("new-customer"):
        doc.name = get_next_customer_id()
        doc.customer_name = doc.customer_name or doc.name
