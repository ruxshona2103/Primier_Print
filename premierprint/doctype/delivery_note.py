from frappe.model.document import Document
import frappe

class DeliveryNote(Document):

    def validate(self):
        """Delivery Note yuborilishidan oldin zaxira yetarli yoki yo'qligini tekshirish."""
        for item_row in self.items:
            # 1. Ombordagi hozirgi miqdorni Bin jadvalidan olish
            current_qty = frappe.db.get_value(
                "Bin",
                {"item_code": item_row.item_code, "warehouse": item_row.warehouse},
                "actual_qty"
            )
            delivery_qty = item_row.qty

            # 2. Zaxira yetarli emasmi?
            if current_qty < delivery_qty:
                frappe.throw(
                    f"QAT'IY CHEKLOV: Yetkazib berish taqiqlanadi. {item_row.item_name} ({item_row.warehouse}) omborida mavjud: {current_qty}, talab: {delivery_qty}.",
                    title="Zaxira Kam"
                )
# Sales Invoice uchun ham xuddi shu kodni takrorlang!
