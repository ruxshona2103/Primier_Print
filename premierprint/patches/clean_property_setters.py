import frappe


def execute():
	# Item, Customer va Supplier uchun barcha Property Setterlarni o'chirish
	doctypes = ['Item', 'Customer', 'Supplier']

	frappe.db.sql("""
        DELETE FROM `tabProperty Setter`
        WHERE doc_type IN %s
    """, (doctypes,))

	# O'zgarishlarni keshdan tozalash
	frappe.clear_cache()
