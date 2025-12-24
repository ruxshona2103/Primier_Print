import frappe
from frappe.model.document import Document
from frappe import _


class StockEntry(Document):
	"""
	Custom Stock Entry Controller for premierprint app

	Versiya: 3.0 (COMPLETE FIX)

	Kritik O'zgarishlar:
	- custom_from_sub_company BUTUNLAY O'CHIRILDI
	- company (Source Company) asosiy maydon
	- custom_to_sub_company (Target Company) asosiy maydon
	- Avtomatik SI, PR, JE yaratish (faqat Перемещение uchun)
	"""

	def validate(self):
		"""Yuborishdan oldin validatsiya"""
		self.validate_scenario_fields()
		self.validate_warehouses()

	def validate_scenario_fields(self):
		"""3 ta ssenariy uchun maydonlarni tekshirish"""

		# SSENARIY 1: Расход по заказу
		if self.stock_entry_type == "Расход по заказу":
			if not self.custom_sales_order:
				frappe.throw(_("Sales Order majburiy: Расход по заказу uchun Sales Order tanlash shart!"))
			if not self.custom_sales_order_item:
				frappe.throw(_("Sales Order Item majburiy: Расход по заказу uchun Sales Order Item tanlash shart!"))

		# SSENARIY 2: Услуги по заказу
		elif self.stock_entry_type == "Услуги по заказу":
			if not self.custom_supplier:
				frappe.throw(_("Supplier majburiy: Услуги по заказу uchun Supplier tanlash shart!"))

		# SSENARIY 3: Перемещение
		elif self.stock_entry_type == "Перемещение":
			if not self.company:
				frappe.throw(_("Company majburiy: Перемещение uchun Company (Source) tanlash shart!"))
			if not self.custom_to_sub_company:
				frappe.throw(_("To Sub Company majburiy: Перемещение uchun To Sub Company (Target) tanlash shart!"))
			if self.company == self.custom_to_sub_company:
				frappe.throw(_("Company va To Sub Company bir xil bo'lishi mumkin emas!"))

	def validate_warehouses(self):
		"""
		Omborlarni kompaniyaga mosligini tekshirish

		Перемещение uchun:
		- Source Warehouse faqat Company (Source) ga tegishli bo'lishi kerak
		- Target Warehouse faqat To Sub Company (Target) ga tegishli bo'lishi kerak
		"""
		if self.stock_entry_type == "Перемещение":
			for item in self.items:
				# Source Warehouse tekshirish (Company ga tegishli bo'lishi kerak)
				if item.s_warehouse:
					source_company = frappe.db.get_value("Warehouse", item.s_warehouse, "company")
					if source_company != self.company:
						frappe.throw(
							_(f"Source Warehouse '{item.s_warehouse}' Company '{self.company}' ga mos emas! "
							f"(Warehouse kompaniyasi: {source_company})")
						)

				# Target Warehouse tekshirish (To Sub Company ga tegishli bo'lishi kerak)
				if item.t_warehouse:
					target_company = frappe.db.get_value("Warehouse", item.t_warehouse, "company")
					if target_company != self.custom_to_sub_company:
						frappe.throw(
							_(f"Target Warehouse '{item.t_warehouse}' To Sub Company '{self.custom_to_sub_company}' ga mos emas! "
							f"(Warehouse kompaniyasi: {target_company})")
						)

	def on_submit(self):
		"""
		Stock Entry yuborilganda avtomatik hujjatlar yaratish

		Faqat "Перемещение" turi uchun:
		- Draft Sales Invoice (Company nomidan)
		- Draft Purchase Receipt (To Sub Company nomidan)
		- Draft Journal Entry (inter-company reconciliation)
		"""
		# Faqat Перемещение turi uchun
		if self.stock_entry_type == "Перемещение":
			self.create_inter_company_transactions()

	def create_inter_company_transactions(self):
		"""
		Компанiyalar o'rtasida Sales Invoice, Purchase Receipt va Journal Entry yaratish (DRAFT)

		Logika:
		- Sales Invoice: Company (Source) nomidan yaratiladi (VATsiz)
		- Purchase Receipt: To Sub Company (Target) nomidan yaratiladi (VATsiz)
		- Journal Entry: Inter-company reconciliation uchun
		"""

		# Inter-company Customer va Supplier topish yoki PLACEHOLDER dan foydalanish
		inter_company_customer = self.get_or_create_inter_company_party("Customer")
		inter_company_supplier = self.get_or_create_inter_company_party("Supplier")

		# --- 1. Sales Invoice yaratish (Source Company uchun, DRAFT, VATsiz) ---
		sales_invoice = frappe.new_doc("Sales Invoice")
		sales_invoice.company = self.company  # Source Company
		sales_invoice.customer = inter_company_customer
		sales_invoice.posting_date = self.posting_date
		sales_invoice.due_date = self.posting_date
		sales_invoice.set_posting_time = 1
		sales_invoice.is_pos = 0

		# VATsiz qilish
		sales_invoice.taxes_and_charges = ""

		for item_row in self.items:
			# Item Price dan avtomatik narx olish
			rate = self.get_item_price(item_row.item_code, self.company) or item_row.basic_rate or 0

			sales_invoice.append("items", {
				"item_code": item_row.item_code,
				"qty": item_row.qty,
				"warehouse": item_row.s_warehouse,
				"rate": rate,
				"cost_center": item_row.cost_center
			})

		try:
			sales_invoice.insert(ignore_permissions=True)
			frappe.msgprint(
				_(f"✅ Sales Invoice {sales_invoice.name} DRAFT holatda yaratildi ({self.company})"),
				title=_("Avtomatik Hujjat"),
				indicator="green"
			)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Sales Invoice yaratishda xato - {self.name}"
			)
			frappe.throw(_(f"Sales Invoice yaratishda xato: {str(e)}"))

		# --- 2. Purchase Receipt yaratish (Target Company uchun, DRAFT, VATsiz) ---
		purchase_receipt = frappe.new_doc("Purchase Receipt")
		purchase_receipt.company = self.custom_to_sub_company  # Target Company
		purchase_receipt.supplier = inter_company_supplier
		purchase_receipt.posting_date = self.posting_date
		purchase_receipt.set_posting_time = 1

		# VATsiz qilish
		purchase_receipt.taxes_and_charges = ""

		for item_row in self.items:
			# Item Price dan avtomatik narx olish
			rate = self.get_item_price(item_row.item_code, self.custom_to_sub_company) or item_row.basic_rate or 0

			purchase_receipt.append("items", {
				"item_code": item_row.item_code,
				"qty": item_row.qty,
				"warehouse": item_row.t_warehouse,
				"rate": rate,
				"cost_center": item_row.cost_center
			})

		try:
			purchase_receipt.insert(ignore_permissions=True)
			frappe.msgprint(
				_(f"✅ Purchase Receipt {purchase_receipt.name} DRAFT holatda yaratildi ({self.custom_to_sub_company})"),
				title=_("Avtomatik Hujjat"),
				indicator="green"
			)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Purchase Receipt yaratishda xato - {self.name}"
			)
			frappe.throw(_(f"Purchase Receipt yaratishda xato: {str(e)}"))

		# --- 3. Journal Entry yaratish (Inter-Company Reconciliation) ---
		self.create_inter_company_journal_entry(sales_invoice, purchase_receipt)

	def get_or_create_inter_company_party(self, party_type):
		"""
		Inter-company Customer yoki Supplier topish yoki PLACEHOLDER dan foydalanish

		Args:
			party_type: "Customer" yoki "Supplier"

		Returns:
			str: Party name (Customer/Supplier)
		"""
		# PLACEHOLDER nomlardan foydalanish
		placeholder_name = "INTER-COMPANY CUSTOMER" if party_type == "Customer" else "INTER-COMPANY SUPPLIER"

		# Agar PLACEHOLDER mavjud bo'lsa, uni qaytarish
		if frappe.db.exists(party_type, placeholder_name):
			return placeholder_name

		# Agar represents_company mantiqidan foydalanmoqchi bo'lsangiz
		if party_type == "Customer":
			# Target Company ni ifodalovchi Customer topish
			party = frappe.db.get_value(
				"Customer",
				{"represents_company": self.custom_to_sub_company},
				"name"
			)
		else:
			# Source Company ni ifodalovchi Supplier topish
			party = frappe.db.get_value(
				"Supplier",
				{"represents_company": self.company},
				"name"
			)

		# Agar topilsa, qaytarish
		if party:
			return party

		# Agar topilmasa, PLACEHOLDER dan foydalanish va ogohlantirish
		frappe.msgprint(
			_(f"⚠️ {party_type} topilmadi. PLACEHOLDER '{placeholder_name}' dan foydalanildi.<br><br>"
			f"<b>Tavsiya:</b> '{placeholder_name}' nomli {party_type} yarating yoki represents_company mantiqini sozlang."),
			title=_(f"{party_type} Ogohlantirish"),
			indicator="orange"
		)

		return placeholder_name

	def get_item_price(self, item_code, company):
		"""
		Item Price dan avtomatik narx olish

		Args:
			item_code: Item kodi
			company: Kompaniya nomi

		Returns:
			float: Item narxi yoki None
		"""
		# Item Price dan narx topish (eng yangi narx)
		price = frappe.db.get_value(
			"Item Price",
			{
				"item_code": item_code,
				"price_list": frappe.db.get_value("Company", company, "default_price_list")
			},
			"price_list_rate"
		)

		# Agar Price List topilmasa, standart Price List dan topish
		if not price:
			price = frappe.db.get_value(
				"Item Price",
				{"item_code": item_code},
				"price_list_rate",
				order_by="modified desc"
			)

		return price

	def create_inter_company_journal_entry(self, sales_invoice, purchase_receipt):
		"""
		Inter-company hisob-kitoblar uchun Journal Entry yaratish (DRAFT)

		Maqsad: Ikki kompaniya o'rtasidagi ichki hisob-kitoblarni to'g'rilash

		Debit:  INTER-COMPANY RECEIVABLE (AKTIV) - Source Company (Debitor qarzi)
		Credit: INTER-COMPANY PAYABLE (MAJBURIYAT) - Target Company (Kreditor qarzi)

		Args:
			sales_invoice: Yaratilgan Sales Invoice (Company/Source)
			purchase_receipt: Yaratilgan Purchase Receipt (To Sub Company/Target)
		"""

		# Umumiy summa (Sales Invoice va Purchase Receipt bir xil bo'lishi kerak)
		total_amount = sales_invoice.total

		# MUHIM: Bu PLACEHOLDER hisob nomlari!
		# Foydalanuvchi o'z Chart of Accounts strukturasiga mos hisob nomlarini kiritishi kerak
		receivable_account = "INTER-COMPANY RECEIVABLE (AKTIV)"
		payable_account = "INTER-COMPANY PAYABLE (MAJBURIYAT)"

		# Journal Entry yaratish
		journal_entry = frappe.new_doc("Journal Entry")
		journal_entry.voucher_type = "Inter Company Journal Entry"
		journal_entry.posting_date = self.posting_date
		journal_entry.company = self.company  # Source Company
		journal_entry.user_remark = (
			f"Inter-company transfer for Stock Entry {self.name} | "
			f"From: {self.company} → To: {self.custom_to_sub_company}"
		)

		# Debit yozuvi (Source Company - Debitor qarzi/Aktiv)
		journal_entry.append("accounts", {
			"account": receivable_account,
			"party_type": "Customer",
			"party": sales_invoice.customer,
			"debit_in_account_currency": total_amount,
			"credit_in_account_currency": 0,
			"reference_type": "Sales Invoice",
			"reference_name": sales_invoice.name
		})

		# Credit yozuvi (Target Company - Kreditor qarzi/Majburiyat)
		journal_entry.append("accounts", {
			"account": payable_account,
			"party_type": "Supplier",
			"party": purchase_receipt.supplier,
			"debit_in_account_currency": 0,
			"credit_in_account_currency": total_amount,
			"reference_type": "Purchase Receipt",
			"reference_name": purchase_receipt.name
		})

		try:
			journal_entry.insert(ignore_permissions=True)
			# DRAFT holatda qoldirish (docstatus = 0)
			frappe.msgprint(
				_(f"✅ Journal Entry {journal_entry.name} DRAFT holatda yaratildi (Inter-company reconciliation)"),
				title=_("Avtomatik Hujjat"),
				indicator="blue"
			)
		except Exception as e:
			frappe.log_error(
				message=frappe.get_traceback(),
				title=f"Journal Entry yaratishda xato - {self.name}"
			)
			frappe.msgprint(
				_(f"⚠️ Journal Entry yaratishda xato: {str(e)}<br><br>"
				f"<b>Sabab:</b> PLACEHOLDER hisob nomlari mavjud emas.<br>"
				f"<b>Yechim:</b> Chart of Accounts da quyidagi hisoblarni yarating:<br>"
				f"1. '{receivable_account}' (Aktiv - Debitor qarzi, Source Company uchun)<br>"
				f"2. '{payable_account}' (Majburiyat - Kreditor qarzi, Target Company uchun)<br><br>"
				f"Yoki Python kodida hisob nomlarini o'zgartiring."),
				title=_("Journal Entry Xatosi"),
				indicator="orange"
			)
