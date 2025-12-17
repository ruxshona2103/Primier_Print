import frappe
from frappe import _
from frappe.utils import flt, formatdate


@frappe.whitelist()
def get_last_sales_price(item_code, customer=None):
	"""
	Eng oxirgi Sales Invoice-dagi narxni topadi

	Args:
		item_code: Item kodi
		customer: Customer (ixtiyoriy - bir xil mijoz uchun)

	Returns:
		dict: {rate: narx, date: sana, invoice: invoice nomi}
	"""

	filters = {
		"item_code": item_code,
		"docstatus": 1  # Faqat submitted
	}

	# Agar customer berilgan bo'lsa, faqat shu mijoz uchun
	if customer:
		filters["parent"] = frappe.db.sql("""
										  SELECT name
										  FROM `tabSales Invoice`
										  WHERE customer = %s
											AND docstatus = 1
										  """, customer, as_list=True)

		if not filters["parent"]:
			return get_last_sales_price_any_customer(item_code)

	# Eng oxirgi Sales Invoice Item-ni topish
	last_item = frappe.db.get_all(
		"Sales Invoice Item",
		filters=filters,
		fields=["rate", "parent", "creation"],
		order_by="creation desc",
		limit=1
	)

	if not last_item:
		# Agar topilmasa, har qanday mijoz uchun
		return get_last_sales_price_any_customer(item_code)

	item = last_item[0]

	# Invoice sanasini olish
	invoice_date = frappe.db.get_value(
		"Sales Invoice",
		item.parent,
		"posting_date"
	)

	return {
		"rate": flt(item.rate, 2),
		"date": formatdate(invoice_date),
		"invoice": item.parent
	}


def get_last_sales_price_any_customer(item_code):
	"""
	Har qanday mijoz uchun eng oxirgi narx
	"""
	last_item = frappe.db.get_all(
		"Sales Invoice Item",
		filters={
			"item_code": item_code,
			"docstatus": 1
		},
		fields=["rate", "parent", "creation"],
		order_by="creation desc",
		limit=1
	)

	if not last_item:
		return {"rate": 0, "date": None, "invoice": None}

	item = last_item[0]
	invoice_date = frappe.db.get_value(
		"Sales Invoice",
		item.parent,
		"posting_date"
	)

	return {
		"rate": flt(item.rate, 2),
		"date": formatdate(invoice_date),
		"invoice": item.parent
	}


@frappe.whitelist()
def get_price_history(item_code, customer=None, limit=5):
	"""
	Narx tarixini ko'rsatish (ixtiyoriy)

	Returns:
		list: [{rate, date, invoice, customer}]
	"""

	sql = """
		  SELECT si_item.rate, \
				 si.posting_date as date,
            si.name as invoice,
            si.customer
		  FROM `tabSales Invoice Item` si_item
			  INNER JOIN `tabSales Invoice` si \
		  ON si_item.parent = si.name
		  WHERE si_item.item_code = %s
			AND si.docstatus = 1
			  {customer_filter}
		  ORDER BY si.posting_date DESC
			  LIMIT %s \
		  """

	customer_filter = ""
	args = [item_code]

	if customer:
		customer_filter = "AND si.customer = %s"
		args.append(customer)

	args.append(limit)

	sql = sql.format(customer_filter=customer_filter)

	history = frappe.db.sql(sql, tuple(args), as_dict=True)

	for record in history:
		record.rate = flt(record.rate, 2)
		record.date = formatdate(record.date)

	return history
