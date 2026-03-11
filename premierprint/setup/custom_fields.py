"""
Custom Fields Setup for Premier Print
--------------------------------------
Creates necessary custom fields for Purchase Invoice LCV integration.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


PREMIERPRINT_MODULE = "premierprint"


PURCHASE_INVOICE_ITEM_CUSTOM_FIELDS = {
	"Purchase Invoice Item": [
		{
			"fieldname": "custom_finished_good",
			"label": "Finished Good",
			"fieldtype": "Link",
			"options": "Item",
			"insert_after": "page_break",
			"module": PREMIERPRINT_MODULE,
		},
		{
			"fieldname": "custom_sales_order",
			"label": "Sales Order",
			"fieldtype": "Link",
			"options": "Sales Order",
			"insert_after": "custom_finished_good",
			"module": PREMIERPRINT_MODULE,
		},
		{
			"fieldname": "custom_sales_order_item",
			"label": "Sales Order Item",
			"fieldtype": "Data",
			"insert_after": "custom_sales_order",
			"module": PREMIERPRINT_MODULE,
		}
	]
}


def create_purchase_invoice_custom_fields():
	"""
	Creates custom fields for Purchase Invoice to track linked LCVs.
	"""
	custom_fields = {
		"Purchase Invoice": [
			{
				"fieldname": "custom_price_variance_lcvs",
				"label": "Price Variance LCVs",
				"fieldtype": "Long Text",
				"insert_after": "remarks",
				"read_only": 1,
				"hidden": 1,
				"no_copy": 1,
				"print_hide": 1,
				"description": "Linked Landed Cost Vouchers for price variance (JSON)",
				"translatable": 0
			}
		]
	}

	create_custom_fields(custom_fields, update=True)
	frappe.db.commit()

	print("✅ Purchase Invoice custom fields created successfully!")


def ensure_purchase_invoice_item_custom_fields():
	"""
	Ensures Purchase Invoice Item tracing fields exist under PremierPrint module.
	"""
	create_custom_fields(PURCHASE_INVOICE_ITEM_CUSTOM_FIELDS, update=True)
	frappe.db.sql(
		"""
		UPDATE `tabCustom Field`
		SET module = %s
		WHERE dt = 'Purchase Invoice Item'
		  AND fieldname IN ('custom_finished_good', 'custom_sales_order', 'custom_sales_order_item')
		""",
		(PREMIERPRINT_MODULE,)
	)
	frappe.db.commit()

	print("✅ Purchase Invoice Item custom fields aligned successfully!")


def setup_all():
	"""
	Main setup function - creates all custom fields.
	"""
	print("🚀 Setting up Premier Print custom fields...")
	create_purchase_invoice_custom_fields()
	ensure_purchase_invoice_item_custom_fields()
	print("✅ All custom fields setup complete!")


if __name__ == "__main__":
	# Run directly via bench console
	setup_all()
