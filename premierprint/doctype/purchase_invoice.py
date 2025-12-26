"""
Professional Purchase Invoice LCV Auto-Creation Module
-------------------------------------------------------
Faqat o'zgargan narxdagi itemlar uchun LCV yaratadi va tannarxga qo'shadi.

ASOSIY LOGIKA:
- PI submit bo'lganda PR bilan narxlarni solishtiradi
- Faqat farq bor itemlar uchun LCV yaratadi
- Farq to'g'ridan-to'g'ri item tannarxiga qo'shiladi
- Bir PI uchun bir LCV (bir nechta PR dan itemlar bo'lsa ham)

REAL MISOLLAR:
Misol 1: PR-001 da Item A = $100, PI-001 da Item A = 12,800,000 UZS (kurs 12,800)
→ LCV: Item A ga +$1,000 qo'shiladi (yangi tannarx: $1,100)

Misol 2: PR-002 da 3 ta item, PI-002 da faqat 2 tasi narxi o'zgargan
→ LCV: faqat o'zgargan 2 ta item uchun yaratiladi
"""

import frappe
from frappe.utils import flt, nowdate
from frappe import _
import json


# ==================== MAIN HOOKS ====================

def auto_create_lcv_for_price_variance(doc, method):
	"""
	PI submit bo'lganda narx farqi uchun LCV yaratadi.

	Qadamlar:
	1. PI va PR narxlarni solishtiradi
	2. Faqat o'zgargan itemlarni topadi
	3. Bir LCV yaratadi (barcha o'zgargan itemlar uchun)
	4. Tannarxga to'g'ridan-to'g'ri qo'shadi
	"""
	# Validations
	if not should_create_lcv(doc):
		return

	# Check custom field
	if not check_custom_field_exists():
		create_custom_field_if_missing()

	# Check for duplicates
	if has_existing_price_variance_lcv(doc):
		frappe.msgprint(
			_("⚠️ Bu PI uchun allaqachon Price Variance LCV yaratilgan."),
			indicator="orange",
			alert=True
		)
		return

	try:
		# Analyze items - faqat o'zgargan narxdagi itemlarni topish
		variance_items = analyze_items_for_variance(doc)

		if not variance_items:
			frappe.msgprint(
				_("ℹ️ Narx farqi topilmadi. Barcha itemlar PR narxida."),
				indicator="blue",
				alert=True
			)
			return

		# Create ONE LCV for ALL changed items
		lcv = create_single_lcv_for_pi(doc, variance_items)

		if not lcv:
			frappe.msgprint(
				_("⚠️ LCV yaratilmadi. Error Log ni tekshiring."),
				indicator="orange",
				alert=True
			)
			return

		# Save LCV reference
		save_lcv_reference(doc, lcv)

		# Show success
		show_success_message(doc, variance_items, lcv)

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


def cancel_linked_lcvs(doc, method):
	"""PI cancel bo'lganda linked LCV ni ham cancel qiladi."""
	lcv_refs = get_lcv_references(doc)

	if not lcv_refs:
		return

	cancelled_count = 0
	errors = []

	for lcv_name in lcv_refs:
		try:
			if not frappe.db.exists("Landed Cost Voucher", lcv_name):
				continue

			lcv_doc = frappe.get_doc("Landed Cost Voucher", lcv_name)

			if lcv_doc.docstatus == 1:
				lcv_doc.flags.ignore_permissions = True
				lcv_doc.cancel()
				cancelled_count += 1

		except Exception as e:
			error_msg = f"LCV {lcv_name}: {str(e)}"
			errors.append(error_msg)
			frappe.log_error(
				title=f"Failed to cancel LCV: {lcv_name}",
				message=frappe.get_traceback()
			)

	if cancelled_count > 0:
		clear_lcv_references(doc)
		frappe.msgprint(
			_("✅ {0} ta Price Variance LCV bekor qilindi.").format(cancelled_count),
			indicator="green",
			alert=True
		)

	if errors:
		frappe.msgprint(
			_("⚠️ Ba'zi LCV larni bekor qilishda xatolik:<br>{0}").format("<br>".join(errors)),
			indicator="orange",
			alert=True
		)


# ==================== VALIDATION ====================

def should_create_lcv(doc):
	"""LCV yaratish kerakligini tekshiradi."""
	# Return Purchase Invoice larni skip qilamiz
	if doc.is_return:
		return False

	# PR reference bor itemlar bormi?
	# Agar PR reference bo'lsa, update_stock holatidan qat'iy nazar LCV yaratamiz
	has_pr_items = any(item.purchase_receipt for item in doc.items)
	if not has_pr_items:
		return False

	return True


def has_existing_price_variance_lcv(doc):
	"""Avval yaratilgan LCV bormi?"""
	lcv_refs = get_lcv_references(doc)

	for lcv_name in lcv_refs:
		if frappe.db.exists("Landed Cost Voucher", lcv_name):
			docstatus = frappe.db.get_value("Landed Cost Voucher", lcv_name, "docstatus")
			if docstatus in [0, 1]:  # Draft yoki Submitted
				return True

	return False


def check_custom_field_exists():
	"""Custom field borligini tekshiradi."""
	return frappe.db.exists("Custom Field", {
		"dt": "Purchase Invoice",
		"fieldname": "custom_price_variance_lcvs"
	})


def create_custom_field_if_missing():
	"""Agar yo'q bo'lsa custom field yaratadi."""
	try:
		if not check_custom_field_exists():
			custom_field = frappe.get_doc({
				"doctype": "Custom Field",
				"dt": "Purchase Invoice",
				"fieldname": "custom_price_variance_lcvs",
				"label": "Price Variance LCVs",
				"fieldtype": "Long Text",
				"insert_after": "is_internal_supplier",
				"read_only": 1,
				"hidden": 1,
				"no_copy": 1,
				"print_hide": 1
			})
			custom_field.insert(ignore_permissions=True)
			frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="Custom Field Creation Failed",
			message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
		)


# ==================== ITEM ANALYSIS ====================

def analyze_items_for_variance(doc):
	"""
	PI itemlarini PR bilan solishtiradi va faqat o'zgargan narxdagilarni topadi.

	Returns:
		list: [{item_data, variance_data, pr_data}, ...]
	"""
	variance_items = []
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	for pi_item in doc.items:
		# PR reference yo'q bo'lsa skip
		if not pi_item.purchase_receipt:
			continue

		# PR item topish
		pr_item_data = get_matched_pr_item(pi_item)
		if not pr_item_data:
			frappe.log_error(
				title=f"PR Item Not Found",
				message=f"PI: {doc.name}, Item: {pi_item.item_code}, PR: {pi_item.purchase_receipt}"
			)
			continue

		# Variance hisoblash (currency conversion bilan)
		variance_data = calculate_variance_in_company_currency(
			pi_item, pr_item_data, doc
		)

		# Skip negligible variances
		if abs(variance_data['variance_usd']) < 0.01:
			continue

		# Qo'shish
		variance_items.append({
			'pi_item': pi_item,
			'pr_item': pr_item_data,
			'variance': variance_data
		})

	return variance_items


def get_matched_pr_item(pi_item):
	"""PR da mos itemni topadi."""
	# 1. Try exact match using pr_detail field
	if hasattr(pi_item, 'pr_detail') and pi_item.pr_detail:
		pr_item = frappe.db.get_value(
			"Purchase Receipt Item",
			pi_item.pr_detail,
			["name", "item_code", "rate", "qty", "parent", "stock_uom"],
			as_dict=1
		)
		if pr_item and pr_item.parent == pi_item.purchase_receipt:
			return pr_item

	# 2. Match by item_code + qty
	pr_items = frappe.db.get_all(
		"Purchase Receipt Item",
		filters={
			"parent": pi_item.purchase_receipt,
			"item_code": pi_item.item_code,
			"docstatus": 1
		},
		fields=["name", "item_code", "rate", "qty", "parent", "stock_uom"],
		order_by="idx"
	)

	for pr_item in pr_items:
		if abs(flt(pr_item.qty) - flt(pi_item.qty)) < 0.001:
			return pr_item

	# 3. First match
	if pr_items:
		return pr_items[0]

	return None


def calculate_variance_in_company_currency(pi_item, pr_item_data, doc):
	"""
	Narx farqini company currency (USD) da hisoblaydi.

	MISOL:
	PR: Item A = $100 (USD)
	PI: Item A = 12,800,000 UZS (kurs 12,800)
	PI USD = 12,800,000 / 12,800 = $1,000
	Variance = $1,000 - $100 = $900 USD
	"""
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	# PI exchange rate
	pi_exchange_rate = flt(doc.conversion_rate) or 1.0

	# PR exchange rate
	pr_doc = frappe.get_cached_doc("Purchase Receipt", pi_item.purchase_receipt)
	pr_exchange_rate = flt(pr_doc.conversion_rate) or 1.0
	pr_currency = pr_doc.currency

	qty = flt(pi_item.qty)

	# Convert rates to USD
	if doc.currency == company_currency:
		pi_rate_usd = flt(pi_item.rate)
	else:
		# UZS -> USD
		pi_rate_usd = flt(pi_item.rate) / pi_exchange_rate

	if pr_currency == company_currency:
		pr_rate_usd = flt(pr_item_data.rate)
	else:
		pr_rate_usd = flt(pr_item_data.rate) / pr_exchange_rate

	# Variance calculation
	rate_diff_usd = pi_rate_usd - pr_rate_usd
	variance_usd = rate_diff_usd * qty

	return {
		'pr_rate': pr_item_data.rate,
		'pr_currency': pr_currency,
		'pr_rate_usd': pr_rate_usd,
		'pi_rate': pi_item.rate,
		'pi_currency': doc.currency,
		'pi_rate_usd': pi_rate_usd,
		'qty': qty,
		'rate_diff_usd': rate_diff_usd,
		'variance_usd': variance_usd,
		'pi_exchange_rate': pi_exchange_rate,
		'company_currency': company_currency
	}


# ==================== LCV CREATION ====================

def create_single_lcv_for_pi(doc, variance_items):
	"""
	Bir PI uchun BITTA LCV yaratadi - barcha o'zgargan itemlar uchun.

	MUHIM: Bir nechta PR dan itemlar bo'lsa ham, BITTA LCV yaratiladi.
	"""
	try:
		company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

		# Total variance
		total_variance_usd = sum(item['variance']['variance_usd'] for item in variance_items)

		# Get all unique PRs
		pr_names = list(set(item['pi_item'].purchase_receipt for item in variance_items))

		# Create LCV
		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = doc.company
		lcv.posting_date = doc.posting_date or nowdate()

		# Add all PRs
		for pr_name in pr_names:
			pr_doc = frappe.get_cached_doc("Purchase Receipt", pr_name)
			lcv.append("purchase_receipts", {
				"receipt_document_type": "Purchase Receipt",
				"receipt_document": pr_name,
				"supplier": pr_doc.supplier,
				"grand_total": pr_doc.grand_total
			})

		# Get account
		variance_account = get_purchase_price_variance_account(doc.company)

		# Add charge
		lcv.append("taxes", {
			"description": f"Price Variance from PI {doc.name} (Auto)",
			"expense_account": variance_account,
			"amount": total_variance_usd  # USD da
		})

		# Save and get items
		lcv.flags.ignore_permissions = True
		lcv.insert()
		lcv.get_items_from_purchase_receipts()

		# Apply item-specific distribution
		apply_variance_to_specific_items(lcv, variance_items)

		# Submit
		lcv.validate()
		lcv.save()
		lcv.submit()

		frappe.db.commit()

		return lcv

	except Exception as e:
		frappe.log_error(
			title=f"LCV Creation Failed for PI: {doc.name}",
			message=f"Error: {str(e)}\n\n{frappe.get_traceback()}"
		)
		return None


def apply_variance_to_specific_items(lcv, variance_items):
	"""
	Faqat o'zgargan itemlarga variance qo'shadi.

	MUHIM: Boshqa itemlarga 0 beradi.
	"""
	# Create mapping: pr_item_name -> variance_usd
	variance_map = {}
	for item_data in variance_items:
		pr_item_name = item_data['pr_item']['name']
		variance_usd = item_data['variance']['variance_usd']
		variance_map[pr_item_name] = variance_usd

	# Apply to LCV items
	total_applied = 0.0
	for lcv_item in lcv.items:
		if lcv_item.purchase_receipt_item in variance_map:
			# O'zgargan item - variance qo'shish
			lcv_item.applicable_charges = variance_map[lcv_item.purchase_receipt_item]
			total_applied += lcv_item.applicable_charges
		else:
			# O'zgarmagan item - 0
			lcv_item.applicable_charges = 0.0

	# Validation
	total_variance = sum(variance_map.values())
	if abs(total_applied - total_variance) > 0.01:
		frappe.log_error(
			title="LCV Distribution Mismatch",
			message=f"Expected: {total_variance}, Applied: {total_applied}, Diff: {abs(total_variance - total_applied)}"
		)


# ==================== ACCOUNT ====================

def get_purchase_price_variance_account(company):
	"""
	'Purchase Price Variance' account ni topadi.
	"""
	abbr = frappe.get_cached_value("Company", company, "abbr")

	# 1. Direct match
	account_name = f"Purchase Price Variance - {abbr}"
	if frappe.db.exists("Account", account_name):
		return account_name

	# 2. Search with keywords
	accounts = frappe.db.get_all(
		"Account",
		filters={
			"company": company,
			"is_group": 0,
			"disabled": 0
		},
		fields=["name", "account_name"]
	)

	for acc in accounts:
		acc_lower = acc.account_name.lower()
		if "purchase price variance" in acc_lower:
			return acc.name
		if "price variance" in acc_lower:
			return acc.name

	# 3. Stock Adjustment
	stock_adj = frappe.db.get_value(
		"Account",
		{
			"company": company,
			"account_type": "Stock Adjustment",
			"is_group": 0
		},
		"name"
	)
	if stock_adj:
		return stock_adj

	# 4. Create if missing
	return create_purchase_price_variance_account(company)


def create_purchase_price_variance_account(company):
	"""
	'Purchase Price Variance' account yaratadi.
	"""
	try:
		abbr = frappe.get_cached_value("Company", company, "abbr")

		# Find parent account
		parent_account = frappe.db.get_value(
			"Account",
			{
				"company": company,
				"account_type": "Stock Adjustment",
				"is_group": 1
			},
			"name"
		)

		if not parent_account:
			# Use Indirect Expenses
			parent_account = frappe.db.get_value(
				"Account",
				{
					"company": company,
					"account_name": "Indirect Expenses",
					"is_group": 1
				},
				"name"
			)

		if not parent_account:
			frappe.throw(_("Parent account topilmadi! 'Stock Adjustment' yoki 'Indirect Expenses' group yarating."))

		# Create account
		account = frappe.get_doc({
			"doctype": "Account",
			"account_name": "Purchase Price Variance",
			"company": company,
			"parent_account": parent_account,
			"account_type": "Stock Adjustment",
			"is_group": 0
		})
		account.insert(ignore_permissions=True)
		frappe.db.commit()

		return account.name

	except Exception as e:
		frappe.log_error(
			title="Failed to create Purchase Price Variance account",
			message=frappe.get_traceback()
		)
		frappe.throw(_("'Purchase Price Variance' account yaratilmadi: {0}").format(str(e)))


# ==================== REFERENCE MANAGEMENT ====================

def save_lcv_reference(doc, lcv):
	"""LCV linkni PI ga saqlaydi."""
	try:
		lcv_refs = get_lcv_references(doc)
		lcv_refs.append(lcv.name)

		frappe.db.set_value(
			"Purchase Invoice",
			doc.name,
			"custom_price_variance_lcvs",
			json.dumps(lcv_refs),
			update_modified=False
		)
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="Failed to save LCV reference",
			message=f"PI: {doc.name}, LCV: {lcv.name}\nError: {str(e)}"
		)


def get_lcv_references(doc):
	"""PI dan LCV linklar oladi."""
	try:
		lcv_json = frappe.db.get_value(
			"Purchase Invoice",
			doc.name,
			"custom_price_variance_lcvs"
		)

		if lcv_json:
			return json.loads(lcv_json)

	except (json.JSONDecodeError, TypeError):
		pass

	return []


def clear_lcv_references(doc):
	"""LCV linklar tozalaydi."""
	try:
		frappe.db.set_value(
			"Purchase Invoice",
			doc.name,
			"custom_price_variance_lcvs",
			None,
			update_modified=False
		)
		frappe.db.commit()

	except Exception as e:
		frappe.log_error(
			title="Failed to clear LCV references",
			message=f"PI: {doc.name}\nError: {str(e)}"
		)


# ==================== USER INTERFACE ====================

def show_success_message(doc, variance_items, lcv):
	"""Muvaffaqiyatli xabar ko'rsatadi."""
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	# Build items table
	items_html = ""
	total_variance = 0.0

	for item_data in variance_items:
		pi_item = item_data['pi_item']
		variance = item_data['variance']

		color = "red" if variance['variance_usd'] > 0 else "green"
		sign = "+" if variance['variance_usd'] > 0 else ""

		items_html += f"""
		<tr>
			<td style='padding: 8px; border: 1px solid #dee2e6;'>{pi_item.item_code}</td>
			<td style='padding: 8px; border: 1px solid #dee2e6;'>{pi_item.item_name[:40]}</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['pr_rate']:.4f} {variance['pr_currency']}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['pi_rate']:.4f} {variance['pi_currency']}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['pr_rate_usd']:.4f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['pi_rate_usd']:.4f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['qty']:.2f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6; color: {color}; font-weight: bold;'>
				{sign}{variance['variance_usd']:,.2f}
			</td>
		</tr>
		"""
		total_variance += variance['variance_usd']

	total_color = "red" if total_variance > 0 else "green"
	total_sign = "+" if total_variance > 0 else ""

	frappe.msgprint(
		f"""
		<div style='padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px; color: white;'>
			<h3 style='margin: 0 0 10px 0; color: white;'>
				✅ Narx Farqi Aniqlandi - Tannarx Yangilandi
			</h3>
			<p style='margin: 0; opacity: 0.9;'>
				Item tannarxlari avtomatik yangilandi. LCV yaratildi.
			</p>
		</div>

		<div style='margin: 20px 0; padding: 15px; background: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>
			<h4 style='margin: 0 0 15px 0; color: #333;'>📊 O'zgargan Itemlar:</h4>

			<table style='width: 100%; border-collapse: collapse; font-size: 13px;'>
				<thead style='background: #f8f9fa;'>
					<tr>
						<th style='padding: 10px; text-align: left; border: 1px solid #dee2e6;'>Item Code</th>
						<th style='padding: 10px; text-align: left; border: 1px solid #dee2e6;'>Item Name</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PR Rate</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PI Rate</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PR Rate (USD)</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PI Rate (USD)</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>Qty</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>Variance (USD)</th>
					</tr>
				</thead>
				<tbody>
					{items_html}
				</tbody>
				<tfoot style='background: #e9ecef; font-weight: bold;'>
					<tr>
						<td colspan='7' style='padding: 12px; text-align: right; border: 1px solid #dee2e6;'>
							JAMI FARQ:
						</td>
						<td style='padding: 12px; text-align: right; border: 1px solid #dee2e6; color: {total_color}; font-size: 15px;'>
							{total_sign}{total_variance:,.2f} {company_currency}
						</td>
					</tr>
				</tfoot>
			</table>
		</div>

		<div style='padding: 15px; background: #d4edda; border-left: 4px solid #28a745; border-radius: 4px;'>
			<p style='margin: 0 0 10px 0; font-weight: bold; color: #155724;'>
				✅ Yaratilgan LCV:
			</p>
			<p style='margin: 0;'>
				<a href='/app/landed-cost-voucher/{lcv.name}' target='_blank'
				   style='color: #155724; font-weight: bold; text-decoration: none; font-size: 15px;'>
					📋 {lcv.name}
				</a>
			</p>
			<p style='margin: 10px 0 0 0; font-size: 12px; color: #155724;'>
				<b>ℹ️ Eslatma:</b> LCV har bir o'zgargan itemning tannarxini yangiladi.
				Keyingi stock operatsiyalar yangi tannarxda bajariladi.
			</p>
		</div>
		""",
		title=_("🎉 Item Tannarxlari Yangilandi"),
		indicator="green",
		alert=True,
		wide=True
	)
