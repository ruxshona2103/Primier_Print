import frappe

def set_smart_id(doc, method):
    """
    Sub Company (Ruscha) maydoniga qarab ID (Naming Series) ni o'zgartirish.
    DocType: Item, Customer
    Trigger: before_insert
    """
    # 1. Sub Company qiymatini olamiz
    # Bu yerda endi "Полиграфия" kabi ruscha so'z qaytadi
    business_unit = doc.get("custom_sub_company")

    if not business_unit:
        return

    # 2. Mantiq: Ruscha Nom -> Seriya
    # DIQQAT: Bu yerdagi so'zlar Customize Form dagi Options bilan 1 ga 1 tushishi shart!
    series_map = {
        "Полиграфия": "П-.######",
        "Реклама":    "Р-.######",
        "Сувенир":    "С-.######"
    }

    target_series = series_map.get(business_unit)

    # 3. Seriyani o'rnatish
    if target_series:
        doc.naming_series = target_series








