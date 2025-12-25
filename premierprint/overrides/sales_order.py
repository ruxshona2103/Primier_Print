"""
Custom Sales Order controller override for auto-increment naming with items
"""
import frappe
from erpnext.selling.doctype.sales_order.sales_order import SalesOrder


class CustomSalesOrder(SalesOrder):
    def autoname(self):
        """
        Override ERPNext's autoname to use format: P10000001/23/45/67
        P - Reklama uchun (rus harfi R)
        10000001 - 8 xonali raqam
        /23/45/67 - itemlarning item_code lari
        """
        # Get next Sales Order ID
        next_id = self.get_next_sales_order_id()

        # Base name: P10000001
        base_name = f"P{next_id}"

        # Add item codes if items exist
        item_codes = self.get_item_codes()

        # Final name
        if item_codes:
            self.name = f"{base_name}/{'/'.join(item_codes)}"
        else:
            self.name = base_name

    def get_item_codes(self):
        """
        Itemlarning code larini olish
        """
        item_codes = []
        if self.items:
            for item in self.items:
                if item.item_code:
                    item_codes.append(str(item.item_code))
        return item_codes

    def get_next_sales_order_id(self):
        """
        Keyingi Sales Order ID ni qaytaradi (8 xonali raqam)
        10000001 dan boshlanadi
        """
        # Get max ID from existing Sales Orders (P bilan boshlanganlar)
        result = frappe.db.sql("""
            SELECT MAX(
                CAST(
                    SUBSTRING(name, 2, 8) AS UNSIGNED
                )
            ) as max_id
            FROM `tabSales Order`
            WHERE name REGEXP '^P[0-9]{8}'
        """, as_dict=True)

        next_id = 10000001
        if result and result[0].get('max_id'):
            next_id = int(result[0]['max_id']) + 1

        # Return 8 digit number with leading zeros
        return str(next_id).zfill(8)

    def on_update(self):
        """
        Sales Order update qilinganda, item o'zgargan bo'lsa name ni yangilash
        """
        super().on_update()

        # Agar Sales Order saqlangan va itemlar o'zgargan bo'lsa
        if self.name and self.name.startswith('P'):
            # Extract base ID (P10000001)
            base_id = self.name.split('/')[0]

            # Rebuild name with current items
            item_codes = self.get_item_codes()

            # Build new name
            if item_codes:
                new_name = f"{base_id}/{'/'.join(item_codes)}"
            else:
                new_name = base_id

            # Rename if changed
            if new_name != self.name:
                frappe.rename_doc('Sales Order', self.name, new_name, force=True, ignore_permissions=True)
                frappe.db.commit()
