import frappe
from frappe.utils import nowdate, flt
from frappe import _
from erpnext.stock.doctype.landed_cost_voucher.landed_cost_voucher import LandedCostVoucher


def auto_create_lcv_from_receipt(doc, method):
	"""
	Purchase Receipt submit bo'lganda avtomatik Landed Cost Voucher yaratadi
	"""
	try:
		# Faqat submitted PR uchun
		if doc.docstatus != 1:
			return

		# Oldin LCV bor-yo'qligini tekshiramiz
		existing_lcv = frappe.db.sql("""
									 SELECT DISTINCT parent
									 FROM `tabLanded Cost Purchase Receipt`
									 WHERE receipt_document = %s
									   AND docstatus != 2
            LIMIT 1
									 """, (doc.name,))

		if existing_lcv:
			frappe.msgprint(
				_("Purchase Receipt {0} uchun LCV allaqachon mavjud: {1}").format(
					doc.name, existing_lcv[0][0]
				),
				indicator="blue",
				alert=True
			)
			return

		# Transport account topamiz
		transport_account = get_default_transport_account(doc.company)

		if not transport_account:
			frappe.msgprint(
				_("⚠️ Transport account topilmadi. LCV yaratilmadi."),
				indicator="orange",
				alert=True
			)
			return

		# Landed cost summasi (2%)
		default_landed_cost = flt(doc.grand_total * 0.02, 2)
		if default_landed_cost < 10:
			default_landed_cost = 10

		# LCV yaratamiz
		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = doc.company
		lcv.posting_date = doc.posting_date or nowdate()

		# Purchase Receipt qo'shamiz
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": doc.name,
			"grand_total": doc.grand_total
		})

		# Xarajat qo'shamiz
		lcv.append("taxes", {
			"expense_account": transport_account,
			"description": f"Auto Landed Cost for {doc.name}",
			"amount": default_landed_cost
		})

		# Saqlash
		lcv.flags.ignore_permissions = True
		lcv.insert()

		# MUHIM: LCV class methodlarini ishlatamiz
		# Bu yerda hech qanday taxmin yo'q - faqat mavjud metodlar
		try:
			# Items olish
			lcv_obj = frappe.get_doc("Landed Cost Voucher", lcv.name)
			lcv_obj.get_items_from_purchase_receipts()

			# Validate va calculate
			lcv_obj.validate()
			lcv_obj.save()

			# Submit
			lcv_obj.submit()

			success_message(lcv_obj.name, doc.name, default_landed_cost, transport_account)

		except Exception as inner_e:
			# Agar avtomatik submit ishlamasa, draft saqlaymiz
			frappe.msgprint(
				_("""
                    ⚠️ LCV yaratildi lekin submit qilinmadi: <a href='/app/landed-cost-voucher/{0}'>{0}</a><br>
                    Sabab: {1}<br><br>
                    Iltimos, qo'lda tekshiring va submit qiling.
                """).format(lcv.name, str(inner_e)),
				indicator="orange",
				alert=True
			)

	except Exception as e:
		frappe.log_error(
			title=f"Auto LCV Failed: {doc.name}",
			message=frappe.get_traceback()
		)
		frappe.msgprint(
			_("❌ Xatolik: {0}").format(str(e)),
			indicator="red",
			alert=True
		)


def get_default_transport_account(company):
	"""Transport account topadi"""

	# 1. Company default
	account = frappe.db.get_value("Company", company, "default_expense_account")
	if account:
		return account

	# 2. Transport nomli
	accounts = frappe.db.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"disabled": 0,
			"account_type": "Expense Account"
		},
		fields=["name", "account_name"]
	)

	for acc in accounts:
		if any(word in acc.account_name.lower() for word in
			   ["transport", "freight", "yuk", "tashish"]):
			return acc.name

	# 3. Birinchi expense account
	if accounts:
		return accounts[0].name

	return None


def success_message(lcv_name, pr_name, amount, account):
	"""Muvaffaqiyatli xabar"""
	frappe.msgprint(
		_("""
            <div style='padding: 15px; background: #d4edda; border-left: 4px solid #28a745;'>
                <h4 style='margin-top: 0; color: #155724;'>✅ Landed Cost Voucher Yaratildi</h4>
                <table style='width: 100%; margin-top: 10px;'>
                    <tr>
                        <td style='padding: 5px;'><b>LCV:</b></td>
                        <td><a href='/app/landed-cost-voucher/{0}' target='_blank'>{0}</a></td>
                    </tr>
                    <tr>
                        <td style='padding: 5px;'><b>Purchase Receipt:</b></td>
                        <td>{1}</td>
                    </tr>
                    <tr>
                        <td style='padding: 5px;'><b>Summa:</b></td>
                        <td>${2:,.2f}</td>
                    </tr>
                    <tr>
                        <td style='padding: 5px;'><b>Account:</b></td>
                        <td>{3}</td>
                    </tr>
                </table>
                <div style='margin-top: 10px; color: #155724;'>
                    <small>✓ Itemlarga avtomatik taqsimlandi va submit qilindi</small>
                </div>
            </div>
        """).format(lcv_name, pr_name, amount, account),
		title=_("Muvaffaqiyat"),
		indicator="green",
		alert=True
	)
