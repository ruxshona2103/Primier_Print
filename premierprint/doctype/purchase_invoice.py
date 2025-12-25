import frappe
from frappe.utils import flt
from frappe import _


def auto_create_lcv_for_price_variance(doc, method):
	"""
	Agar PI narxi PR dan farq qilsa, avtomatik LCV yaratadi.
	Bu narx farqini itemning tannarxiga qo'shadi (LCV orqali).
	"""

	# Faqat stock-related PI lar uchun
	if not doc.update_stock or doc.is_return:
		return

	# Har bir item uchun PR bilan solishtirish
	items_with_variance = []
	total_variance = 0
	pr_dict = {}  # PR lar ro'yxati

	for item in doc.items:
		# PR mavjudligini tekshirish
		if not item.purchase_receipt:
			continue

		# PR item ma'lumotlarini olish
		pr_item = frappe.db.get_value(
			"Purchase Receipt Item",
			{
				"parent": item.purchase_receipt,
				"item_code": item.item_code,
				"docstatus": 1
			},
			["rate", "amount", "qty", "parent"],
			as_dict=1
		)

		if not pr_item:
			continue

		# Narx farqini hisoblash
		rate_diff = flt(item.rate) - flt(pr_item.rate)
		variance = rate_diff * flt(item.qty)

		# Juda kichik farqlarni ignore qilish (rounding errors)
		if abs(variance) < 0.01:
			continue

		items_with_variance.append({
			"item_code": item.item_code,
			"item_name": item.item_name,
			"purchase_receipt": item.purchase_receipt,
			"pr_rate": pr_item.rate,
			"pi_rate": item.rate,
			"qty": item.qty,
			"variance": variance
		})

		total_variance += variance

		# PR ni dict ga qo'shish
		if item.purchase_receipt not in pr_dict:
			pr_dict[item.purchase_receipt] = frappe.get_doc(
				"Purchase Receipt",
				item.purchase_receipt
			)

	# Agar farq yo'q bo'lsa - chiqish
	if not items_with_variance or abs(total_variance) < 0.01:
		return

	# LCV yaratish
	try:
		lcv = create_price_variance_lcv(
			doc,
			items_with_variance,
			total_variance,
			pr_dict
		)

		# Muvaffaqiyatli xabar
		show_success_message(lcv, items_with_variance, total_variance)

	except Exception as e:
		frappe.log_error(
			title=f"Auto LCV Failed for PI: {doc.name}",
			message=frappe.get_traceback()
		)
		frappe.msgprint(
			_("⚠️ LCV yaratishda xatolik: {0}").format(str(e)),
			indicator="red",
			alert=True
		)


def create_price_variance_lcv(pi_doc, items_variance, total_variance, pr_dict):
	"""
	Narx farqi uchun Landed Cost Voucher yaratadi
	"""

	# LCV document yaratish
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = pi_doc.company
	lcv.posting_date = pi_doc.posting_date

	# Purchase Receiptlarni qo'shish
	for pr_name, pr_doc in pr_dict.items():
		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pr_name,
			"supplier": pr_doc.supplier,
			"grand_total": pr_doc.grand_total
		})

	# Price Variance account topish
	variance_account = get_price_variance_account(pi_doc.company)

	# Applicable Charges - narx farqi
	lcv.append("taxes", {
		"description": f"Price Variance from Purchase Invoice {pi_doc.name}",
		"expense_account": variance_account,
		"amount": total_variance
	})

	# Saqlash va hisoblash
	lcv.flags.ignore_permissions = True
	lcv.insert()

	# Itemlarni olish va hisoblash
	lcv.get_items_from_purchase_receipts()
	lcv.validate()
	lcv.save()

	# Submit qilish
	lcv.submit()

	return lcv


def get_price_variance_account(company):
	"""
	Price Variance account topadi yoki birinchi expense accountni qaytaradi
	"""

	# Company abbreviation
	abbr = frappe.get_cached_value("Company", company, "abbr")

	# 1. "Price Variance" account bormi?
	account_name = f"Purchase Price Variance - {abbr}"
	if frappe.db.exists("Account", account_name):
		return account_name

	# 2. "variance" yoki "price difference" so'zi bor accountni topish
	accounts = frappe.db.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"disabled": 0,
			"account_type": ["in", ["Expense Account", "Cost of Goods Sold"]]
		},
		fields=["name", "account_name"]
	)

	for acc in accounts:
		acc_lower = acc.account_name.lower()
		if any(word in acc_lower for word in ["variance", "price", "difference", "narx"]):
			return acc.name

	# 3. Default expense account
	default_account = frappe.db.get_value(
		"Company",
		company,
		"default_expense_account"
	)
	if default_account:
		return default_account

	# 4. Birinchi topilgan expense account
	if accounts:
		return accounts[0].name

	# 5. Agar hech narsa topilmasa - xatolik
	frappe.throw(
		_("Price Variance account topilmadi! Iltimos, Expense Account yarating.")
	)


def show_success_message(lcv, items_variance, total_variance):
	"""
	Muvaffaqiyatli xabar ko'rsatadi
	"""

	# Items jadvalini yaratish
	items_table = ""
	for item in items_variance:
		items_table += f"""
        <tr>
            <td style='padding: 5px;'>{item['item_code']}</td>
            <td style='padding: 5px; text-align: right;'>${item['pr_rate']:.2f}</td>
            <td style='padding: 5px; text-align: right;'>${item['pi_rate']:.2f}</td>
            <td style='padding: 5px; text-align: right;'>{item['qty']}</td>
            <td style='padding: 5px; text-align: right; {"color: red;" if item["variance"] > 0 else "color: green;"}'>${item['variance']:,.2f}</td>
        </tr>
        """

	frappe.msgprint(
		_("""
        <div style='padding: 15px; background: #fff3cd; border-left: 4px solid #ffc107;'>
            <h4 style='margin-top: 0; color: #856404;'>
                📊 Narx Farqi Aniqlandi - LCV Yaratildi
            </h4>
            <p><b>Item tannarxlari yangilandi!</b></p>

            <table style='width: 100%; margin: 10px 0; border-collapse: collapse;'>
                <thead style='background: #f8f9fa;'>
                    <tr>
                        <th style='padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;'>Item</th>
                        <th style='padding: 8px; text-align: right; border-bottom: 2px solid #dee2e6;'>PR Narxi</th>
                        <th style='padding: 8px; text-align: right; border-bottom: 2px solid #dee2e6;'>PI Narxi</th>
                        <th style='padding: 8px; text-align: right; border-bottom: 2px solid #dee2e6;'>Qty</th>
                        <th style='padding: 8px; text-align: right; border-bottom: 2px solid #dee2e6;'>Farq</th>
                    </tr>
                </thead>
                <tbody>
                    {items_table}
                </tbody>
                <tfoot style='background: #f8f9fa; font-weight: bold;'>
                    <tr>
                        <td colspan='4' style='padding: 8px; text-align: right; border-top: 2px solid #dee2e6;'>JAMI:</td>
                        <td style='padding: 8px; text-align: right; border-top: 2px solid #dee2e6; {"color: red;" if total_variance > 0 else "color: green;"}'>${total_variance:,.2f}</td>
                    </tr>
                </tfoot>
            </table>

            <div style='margin-top: 15px; padding: 10px; background: #d4edda; border-left: 3px solid #28a745;'>
                <p style='margin: 0;'><b>✅ LCV Document:</b>
                    <a href='/app/landed-cost-voucher/{lcv_name}' target='_blank' style='color: #155724; font-weight: bold;'>{lcv_name}</a>
                </p>
                <p style='margin: 5px 0 0 0;'><small>
                    Bu LCV itemlarning tannarxini yangiladi. Endi barcha stock operatsiyalar yangi narxda amalga oshiriladi.
                </small></p>
            </div>
        </div>
        """).format(
			items_table=items_table,
			lcv_name=lcv.name,
			total_variance=total_variance
		),
		title=_("Item Tannarxlari Yangilandi"),
		indicator="orange",
		alert=True,
		wide=True
	)
