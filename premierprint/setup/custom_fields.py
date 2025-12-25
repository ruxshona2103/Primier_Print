"""
Custom Fields Setup for Premier Print
--------------------------------------
Creates necessary custom fields for Purchase Invoice LCV integration.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


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


def setup_all():
	"""
	Main setup function - creates all custom fields.
	"""
	print("🚀 Setting up Premier Print custom fields...")
	create_purchase_invoice_custom_fields()
	print("✅ All custom fields setup complete!")


if __name__ == "__main__":
	# Run directly via bench console
	setup_all()
