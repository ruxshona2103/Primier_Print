"""
Landed Cost Voucher (LCV) Management Module - FIXED VERSION
============================================================

ASOSIY TUZATISHLAR:
1. ✅ Har bir PI item uchun alohida variance hisoblash
2. ✅ PR-PI item juftligini unique tracking qilish
3. ✅ Variance distribution xatosini bartaraf etish
4. ✅ Bir xil item turli narxlarda kelganda aralashmaslik

Author: Premier Print Development Team
Version: 2.2-FIXED
Last Updated: 2025-01-12
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate
import json


# ============================================================
# SECTION 1: TRANSPORT COST - AUTO FILL FROM PO
# ============================================================

def auto_fill_transport_from_po(doc, method):
	"""
	Purchase Invoice yaratilganda Purchase Order dan transport xarajatni avtomatik ko'chiradi.
	"""

	if hasattr(doc, 'custom_transport_cost') and doc.custom_transport_cost and flt(
		doc.custom_transport_cost) > 0:
		frappe.logger().debug(
			f"PI {doc.name or 'New'}: Transport cost already set, skipping auto-fill")
		return

	po_names = []
	for item in doc.items:
		if item.purchase_order:
			po_names.append(item.purchase_order)

	if not po_names:
		return

	po_names = list(set(po_names))
	po_transport_data = get_po_transport_data_batch(po_names)

	if not po_transport_data:
		return

	if len(po_transport_data) == 1:
		selected_po_data = po_transport_data[0]
	else:
		selected_po_data = max(
			po_transport_data,
			key=lambda x: flt(x.get('custom_transport_cost', 0))
		)

		frappe.msgprint(
			_(f"⚠️ Bir nechta PO da transport xarajat topildi. "
			  f"Eng kattasi tanlandi: {selected_po_data['name']} "
			  f"({flt(selected_po_data.get('custom_transport_cost', 0)):,.2f})"),
			indicator="orange",
			alert=True
		)

	if hasattr(doc, 'custom_transport_cost'):
		doc.custom_transport_cost = flt(selected_po_data.get('custom_transport_cost', 0))

	if hasattr(doc, 'custom_lcv_currency'):
		doc.custom_lcv_currency = selected_po_data.get('custom_transport_currency') or doc.currency

	if hasattr(doc, 'custom_lcv_exchange_rate'):
		doc.custom_lcv_exchange_rate = flt(
			selected_po_data.get('custom_transport_exchange_rate', 1.0))

	if hasattr(doc, 'custom_lcv_allocation'):
		doc.custom_lcv_allocation = selected_po_data.get('custom_transport_allocation', 'Amount')

	if hasattr(doc, 'custom_source_po'):
		doc.custom_source_po = selected_po_data['name']

	frappe.logger().info(
		f"PI {doc.name or 'New'}: Auto-filled transport from PO {selected_po_data['name']}: "
		f"{doc.custom_transport_cost:,.2f}"
	)


def get_po_transport_data_batch(po_names):
	"""Barcha PO lardan transport data oladi"""
	try:
		po_data = frappe.db.get_all(
			"Purchase Order",
			filters={
				"name": ["in", po_names],
				"docstatus": 1,
				"custom_transport_cost": [">", 0]
			},
			fields=[
				"name",
				"custom_transport_cost",
				"custom_transport_currency",
				"custom_transport_exchange_rate",
				"custom_transport_allocation"
			]
		)
		return po_data
	except Exception as e:
		frappe.logger().error(f"Failed to get PO transport data: {str(e)}")
		return []


def validate_transport_data(doc, method):
	"""PI da transport data ni validatsiya qiladi"""

	if not hasattr(doc, 'custom_transport_cost'):
		return

	if not doc.custom_transport_cost or flt(doc.custom_transport_cost) <= 0:
		return

	if not hasattr(doc, 'custom_lcv_currency') or not doc.custom_lcv_currency:
		if hasattr(doc, 'custom_lcv_currency'):
			doc.custom_lcv_currency = doc.currency

	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	if hasattr(doc, 'custom_lcv_currency') and hasattr(doc, 'custom_lcv_exchange_rate'):
		if doc.custom_lcv_currency != company_currency:
			if not doc.custom_lcv_exchange_rate or flt(doc.custom_lcv_exchange_rate) <= 0:
				doc.custom_lcv_exchange_rate = get_exchange_rate(
					doc.custom_lcv_currency,
					company_currency,
					doc.posting_date or nowdate()
				)

				if not doc.custom_lcv_exchange_rate or flt(doc.custom_lcv_exchange_rate) <= 0:
					frappe.throw(
						_(f"Valyuta kursi topilmadi: {doc.custom_lcv_currency} -> {company_currency}")
					)
		else:
			doc.custom_lcv_exchange_rate = 1.0

	if hasattr(doc, 'custom_lcv_allocation') and not doc.custom_lcv_allocation:
		doc.custom_lcv_allocation = 'Amount'


def get_exchange_rate(from_currency, to_currency, transaction_date):
	"""Valyuta kursini oladi"""
	try:
		from erpnext.setup.utils import get_exchange_rate as frappe_get_exchange_rate
		rate = frappe_get_exchange_rate(from_currency, to_currency, transaction_date, "for_buying")
		return flt(rate)
	except Exception as e:
		frappe.logger().warning(
			f"Failed to get exchange rate {from_currency} -> {to_currency}: {str(e)}")
		return 0.0


# ============================================================
# SECTION 2: TRANSPORT COST - LCV CREATION
# ============================================================

def create_lcv_from_pi(doc, method):
	"""
	Purchase Invoice submit bo'lganda transport xarajati uchun LCV yaratadi.
	"""

	if not hasattr(doc, 'custom_transport_cost'):
		frappe.logger().debug(f"PI {doc.name}: custom_transport_cost field mavjud emas")
		return

	if not doc.custom_transport_cost or flt(doc.custom_transport_cost) <= 0:
		frappe.logger().debug(f"PI {doc.name}: Transport xarajat yo'q")
		return

	pr_list = list(set([d.purchase_receipt for d in doc.items if d.purchase_receipt]))
	if not pr_list:
		frappe.msgprint(
			_("⚠️ Purchase Receipt topilmadi. Transport LCV yaratish uchun PR kerak."),
			indicator='orange',
			alert=True
		)
		return

	lcv_currency = getattr(doc, 'custom_lcv_currency', None) or doc.currency
	lcv_rate = getattr(doc, 'custom_lcv_exchange_rate', None) or 1.0

	if not lcv_rate or flt(lcv_rate) <= 0:
		frappe.msgprint(
			_("⚠️ Valyuta kursi noto'g'ri. Transport LCV yaratilmadi."),
			indicator='orange',
			alert=True
		)
		return

	try:
		company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')
		converted_amount = convert_to_company_currency(
			amount=flt(doc.custom_transport_cost),
			from_currency=lcv_currency,
			to_currency=company_currency,
			exchange_rate=flt(lcv_rate)
		)

		lcv = create_transport_lcv(
			doc=doc,
			pr_list=pr_list,
			transport_amount=converted_amount,
			original_amount=flt(doc.custom_transport_cost),
			original_currency=lcv_currency,
			exchange_rate=flt(lcv_rate)
		)

		source_info = ""
		if hasattr(doc, 'custom_source_po') and doc.custom_source_po:
			source_info = f"<br>📦 Source PO: <a href='/app/purchase-order/{doc.custom_source_po}'>{doc.custom_source_po}</a>"

		frappe.msgprint(
			_("✅ <b>Transport LCV Yaratildi</b><br><br>"
			  "📄 LCV: <a href='/app/landed-cost-voucher/{0}'>{0}</a>{1}<br>"
			  "💰 Transport: {2:,.2f} {3}<br>"
			  "💵 Converted: {4:,.2f} {5}<br>"
			  "📊 Rate: {6:,.4f}").format(
				lcv.name,
				source_info,
				flt(doc.custom_transport_cost),
				lcv_currency,
				converted_amount,
				company_currency,
				flt(lcv_rate)
			),
			indicator='green',
			alert=True
		)

		frappe.logger().info(
			f"Transport LCV {lcv.name} created for PI {doc.name}: "
			f"{converted_amount:,.2f} {company_currency}"
		)

	except Exception as e:
		frappe.log_error(
			message=frappe.get_traceback(),
			title=f"Transport LCV Error - PI: {doc.name}"
		)
		frappe.msgprint(
			_("❌ Transport LCV yaratishda xatolik: {0}").format(str(e)),
			indicator='red',
			alert=True
		)


def create_transport_lcv(doc, pr_list, transport_amount, original_amount,
						 original_currency, exchange_rate):
	"""Transport xarajati uchun LCV yaratadi"""

	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = doc.company
	lcv.posting_date = doc.posting_date

	for pr_name in pr_list:
		pr_grand_total = frappe.db.get_value("Purchase Receipt", pr_name, "grand_total")
		if not pr_grand_total:
			frappe.throw(_(f"Purchase Receipt {pr_name} topilmadi"))

		lcv.append("purchase_receipts", {
			"receipt_document_type": "Purchase Receipt",
			"receipt_document": pr_name,
			"grand_total": flt(pr_grand_total)
		})

	lcv.get_items_from_purchase_receipts()

	if not lcv.items:
		frappe.throw(_("Purchase Receiptlarda itemlar topilmadi"))

	expense_account = get_transport_expense_account(doc.company)

	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')
	description = _("Transport Xarajati: {0:,.2f} {1}").format(original_amount, original_currency)
	if original_currency != company_currency:
		description += _(" (Rate: {0:,.4f}, = {1:,.2f} {2})").format(
			exchange_rate, transport_amount, company_currency
		)

	lcv.append("taxes", {
		"expense_account": expense_account,
		"description": description,
		"amount": flt(transport_amount)
	})

	allocation_method = getattr(doc, 'custom_lcv_allocation', 'Amount')
	if allocation_method == "Qty":
		lcv.distribute_charges_based_on = "Qty"
	elif allocation_method == "Percent":
		lcv.distribute_charges_based_on = "Distribute Manually"
	else:
		lcv.distribute_charges_based_on = "Amount"

	lcv.flags.ignore_permissions = True
	lcv.save()
	lcv.submit()

	frappe.logger().info(f"Transport LCV {lcv.name} created - Amount: {transport_amount:,.2f}")

	return lcv


def get_transport_expense_account(company):
	"""Transport xarajat hisobini topadi"""

	account = frappe.db.get_value(
		"Account",
		filters={
			"account_name": "Transport Xarajati (LCV)",
			"company": company,
			"is_group": 0,
			"disabled": 0
		},
		fieldname="name"
	)

	if account:
		return account

	account = frappe.db.get_value(
		"Account",
		filters={
			"account_name": ["like", "%Transport%"],
			"account_type": ["in", ["Expense Included In Valuation", "Direct Expense"]],
			"company": company,
			"is_group": 0,
			"disabled": 0
		},
		fieldname="name",
		order_by="creation desc"
	)

	if account:
		frappe.logger().warning(f"Using generic transport account: {account}")
		return account

	frappe.throw(
		_("Transport xarajat hisobi topilmadi.<br><br>"
		  "<b>Hisob yarating:</b><br>"
		  "• Account Name: Transport Xarajati (LCV)<br>"
		  "• Account Type: Expense Included In Valuation<br>"
		  "• Company: {0}").format(company)
	)


# ============================================================
# SECTION 3: PRICE VARIANCE LCV - FIXED VERSION
# ============================================================

def auto_create_lcv_for_price_variance(doc, method):
	"""
	PI submit bo'lganda narx farqini aniqlaydi va LCV yaratadi.

	✅ FIXED: Har bir PI item uchun alohida variance hisoblash
	"""

	if not should_create_price_variance_lcv(doc):
		return

	ensure_custom_field_exists()

	if has_existing_price_variance_lcv(doc):
		frappe.msgprint(
			_("⚠️ Bu PI uchun Price Variance LCV allaqachon mavjud."),
			indicator="orange",
			alert=True
		)
		return

	try:
		variance_items = analyze_items_for_variance_fixed(doc)

		if not variance_items:
			frappe.logger().info(f"PI {doc.name}: No price variance found")
			return

		lcv = create_price_variance_lcv_fixed(doc, variance_items)

		if not lcv:
			frappe.msgprint(
				_("⚠️ Price Variance LCV yaratilmadi."),
				indicator="orange",
				alert=True
			)
			return

		save_lcv_reference(doc, lcv)
		show_variance_success_message(doc, variance_items, lcv)

		frappe.logger().info(
			f"Price Variance LCV {lcv.name} created for PI {doc.name}: "
			f"{len(variance_items)} items"
		)

	except Exception as e:
		frappe.log_error(
			title=f"Price Variance LCV Failed - PI: {doc.name}",
			message=frappe.get_traceback()
		)
		frappe.msgprint(
			_("⚠️ Price Variance LCV xatolik: {0}").format(str(e)),
			indicator="red",
			alert=True
		)


def analyze_items_for_variance_fixed(doc):
	"""
	✅ FIXED: Faqat narxida HAQIQIY O'ZGARISH bo'lgan itemlar uchun LCV yaratish

	ASOSIY O'ZGARISH: 
	1. PR Rate == PI Rate bo'lsa → variance = 0 → LCV ga KIRITILMAYDI
	2. Narx farq egilmasa → item skip qilina boradi
	3. Faqat o'zgargani itemlar uchun LCV yaratiladi
	"""

	pi_items_with_pr = [item for item in doc.items if item.purchase_receipt]
	if not pi_items_with_pr:
		return []

	pr_names = list(set(item.purchase_receipt for item in pi_items_with_pr))
	pr_data_map = get_pr_data_batch(pr_names)

	# ✅ FIXED: Har bir PI item uchun alohida PR item topish va TEKSHIRISH
	variance_items = []
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	frappe.logger().info(f"\n{'=' * 60}")
	frappe.logger().info(f"VARIANCE ANALYSIS (FIXED) - PI: {doc.name}")
	frappe.logger().info(f"Tekshirilayotgan itemlar soni: {len(pi_items_with_pr)}")
	frappe.logger().info(f"{'=' * 60}")

	for pi_item in pi_items_with_pr:
		# ✅ Har bir PI item uchun alohida PR item topish
		pr_item = get_matching_pr_item_for_pi_item(pi_item)

		if not pr_item:
			frappe.logger().warning(
				f"PR item not found: {pi_item.item_code} in {pi_item.purchase_receipt}"
			)
			continue

		pr_data = pr_data_map.get(pi_item.purchase_receipt)
		if not pr_data:
			continue

		variance_data = calculate_variance_smart(
			pi_item=pi_item,
			pi_doc=doc,
			pr_item=pr_item,
			pr_data=pr_data,
			company_currency=company_currency
		)

		# DETAILED LOGGING
		frappe.logger().info(
			f"\n✓ PI Item: {pi_item.name} ({pi_item.item_code})\n"
			f"  PR Item: {pr_item['name']} ({pr_item['parent']})\n"
			f"  PR Rate: {variance_data['pr_rate']:.4f} {variance_data['pr_currency']} "
			f"(Converted: {variance_data['pr_rate_company']:.4f} {company_currency})\n"
			f"  PI Rate: {variance_data['pi_rate']:.4f} {variance_data['pi_currency']} "
			f"(Converted: {variance_data['pi_rate_company']:.4f} {company_currency})\n"
			f"  Qty: {variance_data['qty']:.2f}\n"
			f"  Variance: {variance_data['variance_company_currency']:.4f} {company_currency}"
		)

		# ✅ TUZATISH: Agar narx farq juda kichik bo'lsa (< 0.01) → SKIP
		if abs(variance_data['variance_company_currency']) < 0.01:
			frappe.logger().debug(f"  → Skipped (Narxida HECH FARK YO'Q - variance = 0)")
			continue

		# ✅ TUZATISH: Agar rate faqat ko'rsatkich bo'yicha teng bo'lsa → SKIP
		if abs(variance_data['rate_diff']) < 0.0001:
			frappe.logger().debug(f"  → Skipped (Narx reyting teng - rate_diff ≈ 0)")
			continue

		frappe.logger().info(f"  → ✅ LCV GA KIRITILDI (Narx o'zgargani)")

		variance_items.append({
			'pi_item': pi_item,
			'pr_item': pr_item,
			'variance': variance_data
		})

	frappe.logger().info(f"\n{'=' * 60}")
	frappe.logger().info(f"NATIJA: {len(variance_items)} ta item narxi o'zgartirilgan")
	frappe.logger().info(f"SKIP qilingan: {len(pi_items_with_pr) - len(variance_items)} ta item")
	frappe.logger().info(f"{'=' * 60}\n")

	return variance_items


def get_matching_pr_item_for_pi_item(pi_item):
	"""
	✅ FIXED: Har bir PI item uchun to'g'ri PR itemni topish

	Bu funksiya PR da aynan shu PI item bilan bog'langan itemni topadi
	"""

	# PI item reference bilan PR itemni topish
	if pi_item.pr_detail:  # PR item link bor bo'lsa
		pr_item = frappe.db.get_value(
			"Purchase Receipt Item",
			pi_item.pr_detail,
			["name", "parent", "item_code", "rate", "qty", "stock_uom"],
			as_dict=True
		)
		if pr_item:
			return pr_item

	# Agar link bo'lmasa - item_code va PR bo'yicha topish
	pr_items = frappe.db.get_all(
		"Purchase Receipt Item",
		filters={
			"parent": pi_item.purchase_receipt,
			"item_code": pi_item.item_code,
			"docstatus": 1
		},
		fields=["name", "parent", "item_code", "rate", "qty", "stock_uom"],
		order_by="idx asc"  # Birinchi topilganini olish
	)

	if pr_items:
		return pr_items[0]

	return None


def create_price_variance_lcv_fixed(doc, variance_items):
	"""
	✅ FIXED: Har bir itemga to'g'ri variance qo'llash
	"""

	try:
		company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

		total_variance = sum(
			item['variance']['variance_company_currency']
			for item in variance_items
		)

		if abs(total_variance) < 0.01:
			frappe.throw(_("Total variance juda kichik"))

		pr_names = list(set(item['pi_item'].purchase_receipt for item in variance_items))

		lcv = frappe.new_doc("Landed Cost Voucher")
		lcv.company = doc.company
		lcv.posting_date = doc.posting_date or nowdate()

		for pr_name in pr_names:
			pr_doc = frappe.get_cached_doc("Purchase Receipt", pr_name)
			lcv.append("purchase_receipts", {
				"receipt_document_type": "Purchase Receipt",
				"receipt_document": pr_name,
				"supplier": pr_doc.supplier,
				"grand_total": pr_doc.grand_total
			})

		variance_account = get_purchase_price_variance_account(doc.company)

		lcv.append("taxes", {
			"description": f"Price Variance from PI {doc.name} (Auto)",
			"expense_account": variance_account,
			"amount": total_variance
		})

		lcv.flags.ignore_permissions = True
		lcv.insert()
		
		# Get items FIRST
		lcv.get_items_from_purchase_receipts()

		# ✅ CRITICAL: Set to manual distribution BEFORE applying variance
		lcv.distribute_charges_based_on = "Distribute Manually"

		# ✅ FIXED: To'g'ri variance distribution - items oldin olingan bo'lishi kerak
		apply_variance_to_items_fixed(lcv, variance_items)

		# Save changes WITHOUT validation (validation will recalculate)
		lcv.flags.ignore_validate = False
		lcv.save()
		
		# Submit
		lcv.submit()

		frappe.db.commit()

		return lcv

	except Exception as e:
		frappe.log_error(
			title=f"Price Variance LCV Creation Failed - PI: {doc.name}",
			message=frappe.get_traceback()
		)
		return None


def apply_variance_to_items_fixed(lcv, variance_items):
	"""
	✅ FIXED: Har bir itemga faqat o'zining variance ini qo'llash

	TUZATISHLAR:
	1. PR item name orqali aniq matching
	2. Faqat narxida o'zgargan itemlar uchun
	3. Narxida o'zgarmagan itemlar: applicable_charges = 0
	"""

	# Variance map: PR item name -> variance amount
	variance_map = {}
	for item_data in variance_items:
		pr_item_name = item_data['pr_item']['name']
		variance = item_data['variance']['variance_company_currency']

		# ✅ Agar bir xil PR item bir necha marta bo'lsa - qo'shib borish
		if pr_item_name in variance_map:
			variance_map[pr_item_name] += variance
			frappe.logger().warning(
				f"⚠️ Duplicate PR item {pr_item_name} - adding variance: {variance:.2f}"
			)
		else:
			variance_map[pr_item_name] = variance

	frappe.logger().info(f"\n{'=' * 60}")
	frappe.logger().info(f"VARIANCE DISTRIBUTION (FIXED)")
	frappe.logger().info(f"O'zgargan itemlar: {len(variance_map)}")
	frappe.logger().info(f"{'=' * 60}")

	total_applied = 0.0
	items_updated = 0
	items_unchanged = 0

	for lcv_item in lcv.items:
		if lcv_item.purchase_receipt_item in variance_map:
			variance_amount = variance_map[lcv_item.purchase_receipt_item]
			lcv_item.applicable_charges = variance_amount
			total_applied += variance_amount
			items_updated += 1

			sign = "+" if variance_amount > 0 else ""
			frappe.logger().info(
				f"✓ {lcv_item.item_code}: {sign}{variance_amount:,.2f} "
				f"(PR Item: {lcv_item.purchase_receipt_item})"
			)
		else:
			lcv_item.applicable_charges = 0.0
			items_unchanged += 1
			frappe.logger().debug(
				f"○ {lcv_item.item_code}: 0.00 (narxida o'zgarish yo'q) "
				f"(PR Item: {lcv_item.purchase_receipt_item})"
			)

	total_variance = sum(variance_map.values())
	diff = abs(total_applied - total_variance)

	frappe.logger().info(f"\n{'=' * 60}")
	frappe.logger().info(f"DISTRIBUTION SUMMARY:")
	frappe.logger().info(f"  Kutilayotgan jami: {total_variance:,.2f}")
	frappe.logger().info(f"  Qo'yilgan jami:   {total_applied:,.2f}")
	frappe.logger().info(f"  Farq:             {diff:,.2f}")
	frappe.logger().info(f"  Updated items:    {items_updated}")
	frappe.logger().info(f"  Unchanged items:  {items_unchanged}")
	frappe.logger().info(f"{'=' * 60}\n")

	if diff > 0.01:
		error_msg = (
			f"LCV Distribution Mismatch!\n"
			f"Expected: {total_variance:,.2f}\n"
			f"Applied: {total_applied:,.2f}\n"
			f"Difference: {diff:,.2f}"
		)
		frappe.log_error(title="LCV Distribution Error", message=error_msg)
		frappe.throw(_(error_msg))


def cancel_linked_lcvs(doc, method):
	"""PI cancel bo'lganda linked Price Variance LCV larni ham cancel qiladi"""

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
			_("⚠️ Ba'zi LCV xatolik:<br>{0}").format("<br>".join(errors)),
			indicator="orange",
			alert=True
		)


def should_create_price_variance_lcv(doc):
	"""Price Variance LCV yaratish kerakmi?"""

	if doc.is_return:
		return False

	pr_items = [item for item in doc.items if item.purchase_receipt]
	if not pr_items:
		return False

	pr_names = list(set(item.purchase_receipt for item in pr_items))
	for pr_name in pr_names:
		is_return = frappe.db.get_value("Purchase Receipt", pr_name, "is_return")
		if is_return:
			return False

	return True


def has_existing_price_variance_lcv(doc):
	"""Mavjud Price Variance LCV bormi?"""

	lcv_refs = get_lcv_references(doc)

	for lcv_name in lcv_refs:
		if frappe.db.exists("Landed Cost Voucher", lcv_name):
			docstatus = frappe.db.get_value("Landed Cost Voucher", lcv_name, "docstatus")
			if docstatus in [0, 1]:
				return True

	return False


def ensure_custom_field_exists():
	"""Custom field yaratadi (thread-safe)"""

	field_name = "custom_price_variance_lcvs"

	if frappe.db.exists("Custom Field", {
		"dt": "Purchase Invoice",
		"fieldname": field_name
	}):
		return

	try:
		frappe.db.sql("""
			INSERT IGNORE INTO `tabCustom Field`
			(name, dt, fieldname, label, fieldtype, insert_after,
			 read_only, hidden, no_copy, print_hide)
			VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
		""", (
			f"Purchase Invoice-{field_name}",
			"Purchase Invoice",
			field_name,
			"Price Variance LCVs",
			"Long Text",
			"is_internal_supplier",
			1, 1, 1, 1
		))
		frappe.db.commit()
		frappe.logger().info(f"Created custom field: {field_name}")
	except Exception as e:
		if "Duplicate entry" not in str(e):
			frappe.log_error(
				title="Custom Field Creation Failed",
				message=frappe.get_traceback()
			)


def get_pr_data_batch(pr_names):
	"""Barcha PR ma'lumotlarini oladi"""

	pr_data = frappe.db.get_all(
		"Purchase Receipt",
		filters={
			"name": ["in", pr_names],
			"docstatus": 1
		},
		fields=["name", "currency", "conversion_rate", "supplier", "is_return"]
	)

	return {pr['name']: pr for pr in pr_data}


def calculate_variance_smart(pi_item, pi_doc, pr_item, pr_data, company_currency):
	"""
	Narx farqini hisoblaydi - FAQAT HAQIQIY NARX O'ZGARISHINI ANIQLAYDI
	
	LOGIC:
	1. PR rate'ni company currency'ga convert qilish
	2. PI rate'ni company currency'ga convert qilish  
	3. Rate farqini hisoblash (company currency'da)
	4. Total variance = rate_diff * qty
	"""

	qty = flt(pi_item.qty)

	# PR rate → company currency
	pr_rate_company = convert_to_company_currency(
		amount=flt(pr_item['rate']),
		from_currency=pr_data['currency'],
		to_currency=company_currency,
		exchange_rate=flt(pr_data['conversion_rate'])
	)

	# PI rate → company currency
	pi_rate_company = convert_to_company_currency(
		amount=flt(pi_item.rate),
		from_currency=pi_doc.currency,
		to_currency=company_currency,
		exchange_rate=flt(pi_doc.conversion_rate)
	)

	# Rate difference (in company currency)
	rate_diff = pi_rate_company - pr_rate_company
	variance_total = rate_diff * qty

	# ✅ DEBUG LOGGING
	frappe.logger().debug(
		f"\n{'='*60}\n"
		f"VARIANCE CALCULATION:\n"
		f"  PR: {pr_item['rate']:.2f} {pr_data['currency']} "
		f"(rate: {pr_data['conversion_rate']:.4f}) → {pr_rate_company:.2f} {company_currency}\n"
		f"  PI: {pi_item.rate:.2f} {pi_doc.currency} "
		f"(rate: {pi_doc.conversion_rate:.4f}) → {pi_rate_company:.2f} {company_currency}\n"
		f"  Rate Diff: {rate_diff:.2f} {company_currency}\n"
		f"  Qty: {qty:.2f}\n"
		f"  Total Variance: {variance_total:.2f} {company_currency}\n"
		f"{'='*60}"
	)

	return {
		'pr_rate': pr_item['rate'],
		'pr_currency': pr_data['currency'],
		'pr_rate_company': pr_rate_company,
		'pi_rate': pi_item.rate,
		'pi_currency': pi_doc.currency,
		'pi_rate_company': pi_rate_company,
		'qty': qty,
		'rate_diff': rate_diff,
		'variance_company_currency': variance_total,
		'company_currency': company_currency,
		'pr_exchange_rate': pr_data['conversion_rate'],
		'pi_exchange_rate': pi_doc.conversion_rate,
		'has_real_price_change': abs(rate_diff) > 0.0001
	}


def get_purchase_price_variance_account(company):
	"""Purchase Price Variance account ni topadi"""

	abbr = frappe.get_cached_value("Company", company, "abbr")
	account_name = f"Purchase Price Variance - {abbr}"

	if frappe.db.exists("Account", account_name):
		return account_name

	accounts = frappe.db.get_all(
		"Account",
		filters={"company": company, "is_group": 0, "disabled": 0},
		fields=["name", "account_name"]
	)

	for acc in accounts:
		acc_lower = acc.account_name.lower()
		if "purchase price variance" in acc_lower or "price variance" in acc_lower:
			return acc.name

	stock_adj = frappe.db.get_value(
		"Account",
		{"company": company, "account_type": "Stock Adjustment", "is_group": 0, "disabled": 0},
		"name"
	)
	if stock_adj:
		return stock_adj

	return create_purchase_price_variance_account(company)


def create_purchase_price_variance_account(company):
	"""Purchase Price Variance account yaratadi"""

	try:
		abbr = frappe.get_cached_value("Company", company, "abbr")

		parent_account = frappe.db.get_value(
			"Account",
			{"company": company, "account_type": "Stock Adjustment", "is_group": 1},
			"name"
		)

		if not parent_account:
			parent_account = frappe.db.get_value(
				"Account",
				{"company": company, "account_name": "Indirect Expenses", "is_group": 1},
				"name"
			)

		if not parent_account:
			frappe.throw(_("Parent account topilmadi!"))

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
		frappe.throw(_("Account yaratilmadi: {0}").format(str(e)))


# ============================================================
# SECTION 4: SHARED UTILITIES
# ============================================================

def convert_to_company_currency(amount, from_currency, to_currency, exchange_rate):
	"""
	Valyuta konvertatsiyasi - FIXED VERSION
	
	Frappe Logic:
	- conversion_rate = 1 base unit of transaction currency = X units of company currency
	- Agar PI currency = USD, company = UZS, rate = 12000
	  → 1 USD = 12000 UZS
	- Agar PI currency = UZS, company = USD, rate = 0.000083
	  → 1 UZS = 0.000083 USD
	
	Formula: amount_in_company_currency = amount * conversion_rate
	"""

	amount = flt(amount)
	exchange_rate = flt(exchange_rate) or 1.0

	if exchange_rate <= 0:
		frappe.throw(_("Exchange rate 0 bo'lishi mumkin emas"))

	# Agar bir xil valyuta bo'lsa
	if from_currency == to_currency:
		return amount

	# ✅ UNIVERSAL FORMULA: amount * conversion_rate
	# Frappe'da conversion_rate allaqachon to'g'ri yo'nalishda
	return amount * exchange_rate


# ============================================================
# SECTION 5: REFERENCE MANAGEMENT
# ============================================================

def save_lcv_reference(doc, lcv):
	"""LCV linkni saqlaydi"""
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
			message=f"PI: {doc.name}, LCV: {lcv.name}\n{str(e)}"
		)


def get_lcv_references(doc):
	"""LCV linklar oladi"""
	try:
		lcv_json = frappe.db.get_value("Purchase Invoice", doc.name, "custom_price_variance_lcvs")
		if lcv_json:
			return json.loads(lcv_json)
	except (json.JSONDecodeError, TypeError):
		pass
	return []


def clear_lcv_references(doc):
	"""LCV linklar tozalaydi"""
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
			message=f"PI: {doc.name}\n{str(e)}"
		)


# ============================================================
# SECTION 6: USER INTERFACE
# ============================================================

def show_variance_success_message(doc, variance_items, lcv):
	"""Success message ko'rsatadi - FAQAT O'ZGARGAN ITEMLARNI"""

	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	items_html = ""
	total_variance = 0.0

	for item_data in variance_items:
		pi_item = item_data['pi_item']
		variance = item_data['variance']

		color = "red" if variance['variance_company_currency'] > 0 else "green"
		sign = "+" if variance['variance_company_currency'] > 0 else ""

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
				{variance['pr_rate_company']:.4f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['pi_rate_company']:.4f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6;'>
				{variance['qty']:.2f}
			</td>
			<td style='padding: 8px; text-align: right; border: 1px solid #dee2e6; color: {color}; font-weight: bold;'>
				{sign}{variance['variance_company_currency']:,.2f}
			</td>
		</tr>
		"""
		total_variance += variance['variance_company_currency']

	total_color = "red" if total_variance > 0 else "green"
	total_sign = "+" if total_variance > 0 else ""

	# ✅ TUZATISH: Qancha item skip qilindi
	total_items = len(doc.items)
	changed_items = len(variance_items)
	unchanged_items = total_items - changed_items

	frappe.msgprint(
		f"""
		<div style='padding: 20px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
		            border-radius: 8px; color: white;'>
			<h3 style='margin: 0 0 10px 0; color: white;'>
				✅ Narx Farqi Aniqlandi
			</h3>
			<p style='margin: 0; opacity: 0.9;'>
				{changed_items} ta itemning narxi o'zgartirilgan, {unchanged_items} ta item narxida o'zgarish yo'q
			</p>
		</div>

		<div style='margin: 20px 0; padding: 15px; background: white; border-radius: 8px;
		            box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>
			<h4 style='margin: 0 0 15px 0; color: #333;'>📊 O'zgargan Itemlar ({changed_items}/{total_items}):</h4>

			<table style='width: 100%; border-collapse: collapse; font-size: 13px;'>
				<thead style='background: #f8f9fa;'>
					<tr>
						<th style='padding: 10px; text-align: left; border: 1px solid #dee2e6;'>Item Code</th>
						<th style='padding: 10px; text-align: left; border: 1px solid #dee2e6;'>Item Name</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PR Rate</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PI Rate</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PR Rate ({company_currency})</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>PI Rate ({company_currency})</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>Qty</th>
						<th style='padding: 10px; text-align: right; border: 1px solid #dee2e6;'>Variance ({company_currency})</th>
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
						<td style='padding: 12px; text-align: right; border: 1px solid #dee2e6;
						           color: {total_color}; font-size: 15px;'>
							{total_sign}{total_variance:,.2f} {company_currency}
						</td>
					</tr>
				</tfoot>
			</table>
		</div>

		<div style='padding: 15px; background: #d4edda; border-left: 4px solid #28a745;
		            border-radius: 4px;'>
			<p style='margin: 0 0 10px 0; font-weight: bold; color: #155724;'>
				✅ Yaratilgan LCV:
			</p>
			<p style='margin: 0;'>
				<a href='/app/landed-cost-voucher/{lcv.name}' target='_blank'
				   style='color: #155724; font-weight: bold; text-decoration: none; font-size: 15px;'>
					📋 {lcv.name}
				</a>
			</p>
		</div>

		<div style='padding: 12px; background: #cfe2ff; border-left: 4px solid #0d6efd;
		            border-radius: 4px; margin-top: 15px;'>
			<p style='margin: 0; color: #084298; font-size: 12px;'>
				💡 Faqat narxida <b>HAQIQIY O'ZGARGAN</b> {changed_items} ta item LCV ga kiritildi.
				{unchanged_items} ta itemning narxida o'zgarish yo'q shuning uchun skip qilindi.
			</p>
		</div>
		""",
		title=_("🎉 Item Tannarxlari Yangilandi"),
		indicator="green",
		alert=True,
		wide=True
	)
