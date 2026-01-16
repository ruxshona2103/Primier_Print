import frappe

def set_naming_series(doc, method):
    mapping = {
        "Premier Print": "ПП-.#######",
        "Полиграфия": "П-.########",
        "Реклама": "Р-.#######",
        "Сувенир": "С-.#######"
    }

    try:
        if doc.company and doc.company in mapping:
            doc.naming_series = mapping[doc.company]
            frappe.logger().info(f"PremierPrint: Naming Series FORCE SET to {doc.naming_series} for {doc.company}")
            print(f"DEBUG: Naming Series set to {doc.naming_series}")
        else:
            # Fallback for unknown companies: Use first 3 letters uppercase
            if doc.company:
                prefix = doc.company[:3].upper()
                doc.naming_series = f"{prefix}-.#######"
                print(f"DEBUG: Fallback Naming Series set to {doc.naming_series}")
            
    except Exception as e:
        frappe.log_error(f"Error in set_naming_series: {str(e)}", "PremierPrint Error")
        print(f"ERROR in set_naming_series: {str(e)}")