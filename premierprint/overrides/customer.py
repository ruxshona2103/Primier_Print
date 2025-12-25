"""
Custom Customer controller override for auto-increment naming
"""
import frappe
from erpnext.selling.doctype.customer.customer import Customer


class CustomCustomer(Customer):
    def autoname(self):
        """
        Override ERPNext's autoname to use simple numeric IDs: 1, 2, 3, 4...
        """
        # Get next ID from our custom function
        from premierprint.utils.naming import get_next_customer_id

        next_id = get_next_customer_id()
        self.name = next_id

        # Set customer_name if not provided
        if not self.customer_name:
            self.customer_name = next_id
