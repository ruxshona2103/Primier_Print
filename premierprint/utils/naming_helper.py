"""
Naming helper functions for custom DocType naming
"""
import frappe


def get_category_from_series(naming_series, doctype_code):
    """
    naming_series dan kategoriya kodini olish

    Args:
        naming_series: Series string (e.g., "PR-", "PSE-")
        doctype_code: DocType kodi (e.g., "pr", "se")

    Returns:
        Category code (e.g., "Рpr", "Пse")
    """
    if not naming_series:
        return f"P{doctype_code}"

    # naming_series format: "PR-", "PPR-", "PS-"
    # Extract: PR, PPR, PS
    series = naming_series.replace("-", "").replace("YYYY", "").replace(".", "").strip()
    if series:
        return series

    return f"P{doctype_code}"


def get_item_codes(doc):
    """
    Document'dan item code'larni olish

    Args:
        doc: Document object

    Returns:
        List of item codes
    """
    item_codes = []
    if hasattr(doc, 'items') and doc.items:
        for item in doc.items:
            if hasattr(item, 'item_code') and item.item_code:
                item_codes.append(str(item.item_code))
    return item_codes


def get_next_id(doctype, category_code):
    """
    Keyingi ID ni qaytaradi (7 xonali raqam)

    Args:
        doctype: DocType name
        category_code: Category code (e.g., "Рpr")

    Returns:
        7 digit number string with leading zeros
    """
    # Get max ID from existing documents
    result = frappe.db.sql("""
        SELECT MAX(
            CAST(
                SUBSTRING(name, %s, 7) AS UNSIGNED
            )
        ) as max_id
        FROM `tab{doctype}`
        WHERE name REGEXP %s
    """.format(doctype=doctype), (len(category_code) + 1, f'^{category_code}[0-9]{{7}}'), as_dict=True)

    next_id = 1
    if result and result[0].get('max_id'):
        next_id = int(result[0]['max_id']) + 1

    # Return 7 digit number with leading zeros
    return str(next_id).zfill(7)


def build_name_with_items(base_name, item_codes):
    """
    Base name va item code'lardan to'liq name yasash

    Args:
        base_name: Base name (e.g., "Рpr0000001")
        item_codes: List of item codes

    Returns:
        Full name (e.g., "Рpr0000001/23/45")
    """
    if item_codes:
        return f"{base_name}/{'/'.join(item_codes)}"
    return base_name
