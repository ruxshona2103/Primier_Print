import frappe

def set_naming_series(doc, method):
    mapping = {
        "Premier Print": "ПП-.#######",
        "Полиграфия": "П-.########",
        "Реклама": "Р-.#######",
        "Сувенир": "С-.#######"
    }

    if doc.company in mapping:
        # Tizimga aniq formatni (panjaralari bilan) majburlab ko'rsatamiz
        doc.naming_series = mapping[doc.company]