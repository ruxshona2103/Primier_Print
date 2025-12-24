import frappe
from frappe.model.document import Document


class StockEntry(Document):
	def validate(self):
		"""Yuborishdan oldin validatsiya"""
		self.validate_scenario_fields()
		self.validate_warehouses()

	def validate_scenario_fields(self):
		"""3 ta ssenariy uchun maydonlarni tekshirish"""

		# SSENARIY 1: Расход по заказу
		if self.stock_entry_type == "Расход по заказу":
			if not self.custom_sales_order:
				frappe.throw("Sales Order majburiy: Расход по заказу uchun Sales Order tanlash shart!")
			if not self.custom_sales_order_item:
				frappe.throw("Sales Order Item majburiy: Расход по заказу uchun Sales Order Item tanlash shart!")

		# SSENARIY 2: Услуги по заказу
		elif self.stock_entry_type == "Услуги по заказу":
			if not self.custom_supplier:
				frappe.throw("Supplier majburiy: Услуги по заказу uchun Supplier tanlash shart!")

		# SSENARIY 3: Перемещение
		elif self.stock_entry_type == "Перемещение":
			if not self.custom_from_sub_company:
				frappe.throw("From Sub Company majburiy: Перемещение uchun From Sub Company tanlash shart!")
			if not self.custom_to_sub_company:
				frappe.throw("To Sub Company majburiy: Перемещение uchun To Sub Company tanlash shart!")
			if self.custom_from_sub_company == self.custom_to_sub_company:
				frappe.throw("From va To Sub Company bir xil bo'lishi mumkin emas!")

	def validate_warehouses(self):
		"""Omborlarni sub-kompaniyaga mosligini tekshirish"""
		if self.stock_entry_type == "Перемещение":
			for item in self.items:
				# Source Warehouse tekshirish
				if item.s_warehouse:
					source_company = frappe.db.get_value("Warehouse", item.s_warehouse, "company")
					if source_company != self.custom_from_sub_company:
						frappe.throw(
							f"Source Warehouse '{item.s_warehouse}' From Sub Company '{self.custom_from_sub_company}' ga mos emas! "
							f"(Warehouse kompaniyasi: {source_company})"
						)

				# Target Warehouse tekshirish
				if item.t_warehouse:
					target_company = frappe.db.get_value("Warehouse", item.t_warehouse, "company")
					if target_company != self.custom_to_sub_company:
						frappe.throw(
							f"Target Warehouse '{item.t_warehouse}' To Sub Company '{self.custom_to_sub_company}' ga mos emas! "
							f"(Warehouse kompaniyasi: {target_company})"
						)

	def on_submit(self):
		"""Stock Entry yuborilganda avtomatik hujjatlar yaratish"""

		# Faqat Перемещение turi uchun
		if self.stock_entry_type == "Перемещение":
			self.create_inter_company_transactions()

	def create_inter_company_transactions(self):
		"""Sub-kompaniyalar o'rtasida Sales Invoice va Purchase Receipt yaratish"""

		# Inter-company Customer va Supplier topish
		inter_company_customer = self.get_inter_company_customer()
		inter_company_supplier = self.get_inter_company_supplier()

		# --- 1. Sales Invoice yaratish (Source Company uchun) ---
		sales_invoice = frappe.new_doc("Sales Invoice")
		sales_invoice.company = self.custom_from_sub_company
		sales_invoice.customer = inter_company_customer
		sales_invoice.posting_date = self.posting_date
		sales_invoice.due_date = self.posting_date
		sales_invoice.set_posting_time = 1

		for item_row in self.items:
			sales_invoice.append("items", {
				"item_code": item_row.item_code,
				"qty": item_row.qty,
				"warehouse": item_row.s_warehouse,
				"rate": item_row.basic_rate,
				"cost_center": item_row.cost_center
			})

		try:
			sales_invoice.insert()
			frappe.msgprint(
				f"✅ Sales Invoice {sales_invoice.name} yaratildi ({self.custom_from_sub_company})",
				title="Avtomatik Hujjat",
				indicator="green"
			)
		except Exception as e:
			frappe.throw(f"Sales Invoice yaratishda xato: {str(e)}")

		# --- 2. Purchase Receipt yaratish (Target Company uchun) ---
		purchase_receipt = frappe.new_doc("Purchase Receipt")
		purchase_receipt.company = self.custom_to_sub_company
		purchase_receipt.supplier = inter_company_supplier
		purchase_receipt.posting_date = self.posting_date
		purchase_receipt.set_posting_time = 1

		for item_row in self.items:
			purchase_receipt.append("items", {
				"item_code": item_row.item_code,
				"qty": item_row.qty,
				"warehouse": item_row.t_warehouse,
				"rate": item_row.basic_rate,
				"cost_center": item_row.cost_center
			})

		try:
			purchase_receipt.insert()
			frappe.msgprint(
				f"✅ Purchase Receipt {purchase_receipt.name} yaratildi ({self.custom_to_sub_company})",
				title="Avtomatik Hujjat",
				indicator="green"
			)
		except Exception as e:
			frappe.throw(f"Purchase Receipt yaratishda xato: {str(e)}")

	def get_inter_company_customer(self):
		"""Inter-company Customer topish (Target Company asosida)"""
		customer = frappe.db.get_value(
			"Customer",
			{"represents_company": self.custom_to_sub_company},
			"name"
		)

		if not customer:
			frappe.throw(
				f"Inter-Company Customer topilmadi! "
				f"'{self.custom_to_sub_company}' kompaniyasi uchun Customer yaratish kerak. "
				f"(Customer DocType > represents_company = '{self.custom_to_sub_company}')"
			)

		return customer

	def get_inter_company_supplier(self):
		"""Inter-company Supplier topish (Source Company asosida)"""
		supplier = frappe.db.get_value(
			"Supplier",
			{"represents_company": self.custom_from_sub_company},
			"name"
		)

		if not supplier:
			frappe.throw(
				f"Inter-Company Supplier topilmadi! "
				f"'{self.custom_from_sub_company}' kompaniyasi uchun Supplier yaratish kerak. "
				f"(Supplier DocType > represents_company = '{self.custom_from_sub_company}')"
			)

		return supplier
