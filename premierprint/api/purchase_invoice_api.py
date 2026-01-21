import frappe

@frappe.whitelist()
def get_original_pr_rates(pr_names):
    """
    Purchase Receipt dan asl narxlarni olish.
    Bu metod whitelisted, shuning uchun barcha foydalanuvchilar foydalanishi mumkin.
    
    Args:
        pr_names: Purchase Receipt nomlari ro'yxati (JSON string)
    
    Returns:
        dict: {pr_detail_name: rate, parent|item_code: rate}
    """
    import json
    
    if isinstance(pr_names, str):
        pr_names = json.loads(pr_names)
    
    if not pr_names:
        return {}
    
    # Purchase Receipt Item dan narxlarni olish
    pr_items = frappe.get_all(
        'Purchase Receipt Item',
        filters={'parent': ['in', pr_names]},
        fields=['parent', 'name', 'item_code', 'rate', 'base_rate']
    )
    
    result = {}
    for pr_item in pr_items:
        # pr_detail (name) bo'yicha saqlash
        result[pr_item.name] = pr_item.rate
        # parent|item_code bo'yicha ham saqlash (backup)
        key = f"{pr_item.parent}|{pr_item.item_code}"
        if key not in result:
            result[key] = pr_item.rate
    
    return result
