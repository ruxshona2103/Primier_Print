import frappe
from frappe.model.document import Document


class StockEntry(Document):
	def on_submit(self):
		"""Stock Entry muvaffaqiyatli yuborilgandan so'ng ishlaydi."""

		# Faqat Peremeshenya turini tekshirish
		if self.stock_entry_type == "Peremeshenya":

			# --- Yuboruvchi Kompaniya (Sales Invoice yaratish) ---
			sales_invoice = frappe.new_doc("Sales Invoice")
			sales_invoice.company = self.company  # Source Company
			sales_invoice.posting_date = self.posting_date
			sales_invoice.due_date = self.posting_date  # Yoki kerakli sana
			sales_invoice.set_draft()  # Draft holatida saqlash

			# Har bir mahsulotni qo'shish
			for item_row in self.items:
				sales_invoice.append("items", {
					"item_code": item_row.item_code,
					"qty": item_row.qty,
					"warehouse": item_row.source_warehouse,
					"rate": item_row.basic_rate,  # Qiymatni Stock Entry'dan olamiz
					"is_taxable": "No"  # VAT/QQS yo'q
				})

			# Keyinchalik qo'shiladi: Inter-Company Customer (Buxgalteriya Talabi)
			sales_invoice.customer = "INTER-COMPANY-CUSTOMER-CODE"

			try:
				sales_invoice.insert()
			except Exception as e:
				frappe.throw(f"Sales Invoice yaratishda xato: {e}")

			# --- Qabul Qiluvchi Kompaniya (Purchase Receipt yaratish) ---
			purchase_receipt = frappe.new_doc("Purchase Receipt")
			# Qabul qiluvchi kompaniya Stock Entry ichida aniq belgilanmagan, shuning uchun topish shart!
			# Quyida taxminiy topish logikasi berilgan:
			target_company = frappe.db.get_value("Warehouse", self.items[0].target_warehouse,
												 "company")

			purchase_receipt.company = target_company  # Target Company
			purchase_receipt.posting_date = self.posting_date
			purchase_receipt.set_draft()  # Draft holatida saqlash

			for item_row in self.items:
				purchase_receipt.append("items", {
					"item_code": item_row.item_code,
					"qty": item_row.qty,
					"warehouse": item_row.target_warehouse,
					"rate": item_row.basic_rate,  # Qiymatni Stock Entry'dan olamiz
				})

			# Keyinchalik qo'shiladi: Inter-Company Supplier (Buxgalteriya Talabi)
			purchase_receipt.supplier = "INTER-COMPANY-SUPPLIER-CODE"

			try:
				purchase_receipt.insert()
			except Exception as e:
				frappe.throw(f"Purchase Receipt yaratishda xato: {e}")

		# --- premierprint/premierprint/doctype/stock_entry/stock_entry.py ---

		def on_submit(self):
			if self.stock_entry_type == "Peremeshenya":
				# 1. Kompaniyalar aniqlanishi (DocType'dagi maydonlar orqali)
				source_company = self.from_sub_company
				target_company = self.to_sub_company

				# 2. Sales Invoice yaratish (Source Company uchun)
				self.create_sales_invoice_for_source(source_company, target_company)

				# 3. Purchase Receipt yaratish (Target Company uchun)
				self.create_purchase_receipt_for_target(source_company, target_company)

				# 4. GL Ledger To'g'rilash (Journal Entry yaratish)
				# Bu vazifa quyidagi hisob nomlari aniqlangandan keyin yoziladi!
				self.create_inter_company_journal_entry(source_company, target_company)

			frappe.msgprint(
				f"Peremeshenya muvaffaqiyatli! {target_company} uchun DRAFT Purchase Receipt va {self.company} uchun DRAFT Sales Invoice yaratildi.",
				title="Avtomatik Hujjatlar"
			)
