"""
Professional Purchase Invoice LCV Auto-Creation Module
-------------------------------------------------------
Automatically creates Landed Cost Vouchers when Purchase Invoice prices
differ from Purchase Receipt prices, ensuring accurate inventory valuation.

Features:
- Item-specific price variance tracking
- Multi-PR support (separate LCV per PR)
- Currency conversion (UZS -> USD)
- Duplicate prevention
- Cancel handling
"""

import frappe
from frappe.utils import flt, nowdate
from frappe import _
import json


# ==================== MAIN HOOKS ====================

def auto_create_lcv_for_price_variance(doc, method):
	"""
	Main hook: Creates LCVs for price variances between PR and PI.
	Called on Purchase Invoice submit.

	Args:
		doc: Purchase Invoice document
		method: Hook method name (on_submit)
	"""
	# Validations
	if not should_create_lcv(doc):
		return

	# Check for duplicate LCVs
	if has_existing_price_variance_lcv(doc):
		frappe.msgprint(
			_("⚠️ Bu PI uchun allaqachon Price Variance LCV yaratilgan."),
			indicator="orange",
			alert=True
		)
		return

	try:
		# Analyze items and group by PR
		pr_groups = analyze_and_group_items_by_pr(doc)

		if not pr_groups:
			return  # No variance found

		# Create separate LCV for each PR
		created_lcvs = []
		for pr_name, items_data in pr_groups.items():
			lcv = create_lcv_for_pr_group(doc, pr_name, items_data)
			if lcv:
				created_lcvs.append(lcv)

		# Save LCV references to PI
		save_lcv_references(doc, created_lcvs)

		# Show success message
		show_success_message(doc, pr_groups, created_lcvs)

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
	"""
	Cancel hook: Cancels all linked Price Variance LCVs when PI is cancelled.

	Args:
		doc: Purchase Invoice document
		method: Hook method name (on_cancel)
	"""
	lcv_refs = get_lcv_references(doc)

	if not lcv_refs:
		return

	cancelled_count = 0
	errors = []

	for lcv_name in lcv_refs:
		try:
			lcv_doc = frappe.get_doc("Landed Cost Voucher", lcv_name)

			if lcv_doc.docstatus == 1:  # Submitted
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

	# Clear references
	if cancelled_count > 0:
		clear_lcv_references(doc)

	# Show result
	if cancelled_count > 0:
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


# ==================== VALIDATION & CHECKS ====================

def should_create_lcv(doc):
	"""
	Checks if LCV should be created for this PI.

	Returns:
		bool: True if should create, False otherwise
	"""
	# Only for stock-updating PIs
	if not doc.update_stock:
		return False

	# Not for return invoices
	if doc.is_return:
		return False

	# Must have items with PR references
	has_pr_items = any(item.purchase_receipt for item in doc.items)
	if not has_pr_items:
		return False

	return True


def has_existing_price_variance_lcv(doc):
	"""
	Checks if price variance LCVs already exist for this PI.

	Returns:
		bool: True if LCVs exist, False otherwise
	"""
	lcv_refs = get_lcv_references(doc)
	return bool(lcv_refs)


# ==================== ITEM ANALYSIS & GROUPING ====================

def analyze_and_group_items_by_pr(doc):
	"""
	Analyzes PI items, matches with PR items, and groups by PR.

	Args:
		doc: Purchase Invoice document

	Returns:
		dict: {pr_name: {
			'items': [...],
			'total_variance': float,
			'pr_doc': object
		}}
	"""
	pr_groups = {}

	for pi_item in doc.items:
		# Skip items without PR reference
		if not pi_item.purchase_receipt:
			continue

		# Get matched PR item (specific line)
		pr_item_data = get_matched_pr_item(pi_item)

		if not pr_item_data:
			continue

		# Calculate variance
		variance_data = calculate_item_variance(pi_item, pr_item_data, doc)

		# Skip negligible variances
		if abs(variance_data['variance_company_currency']) < 0.01:
			continue

		# Group by PR
		pr_name = pi_item.purchase_receipt

		if pr_name not in pr_groups:
			pr_groups[pr_name] = {
				'items': [],
				'total_variance': 0.0,
				'pr_doc': frappe.get_doc("Purchase Receipt", pr_name)
			}

		pr_groups[pr_name]['items'].append(variance_data)
		pr_groups[pr_name]['total_variance'] += variance_data['variance_company_currency']

	# Remove groups with zero total variance
	pr_groups = {k: v for k, v in pr_groups.items() if abs(v['total_variance']) > 0.01}

	return pr_groups


def get_matched_pr_item(pi_item):
	"""
	Finds the exact matching PR item using purchase_receipt_item field.

	Args:
		pi_item: Purchase Invoice Item

	Returns:
		dict: PR item data or None
	"""
	# Try exact match first (using purchase_receipt_item reference)
	if pi_item.purchase_receipt_item:
		pr_item = frappe.db.get_value(
			"Purchase Receipt Item",
			pi_item.purchase_receipt_item,
			["name", "item_code", "rate", "qty", "parent", "stock_uom"],
			as_dict=1
		)

		if pr_item and pr_item.parent == pi_item.purchase_receipt:
			return pr_item

	# Fallback: Match by PR + item_code + qty (for older data)
	pr_item = frappe.db.get_value(
		"Purchase Receipt Item",
		{
			"parent": pi_item.purchase_receipt,
			"item_code": pi_item.item_code,
			"qty": pi_item.qty,
			"docstatus": 1
		},
		["name", "item_code", "rate", "qty", "parent", "stock_uom"],
		as_dict=1
	)

	return pr_item


def calculate_item_variance(pi_item, pr_item_data, doc):
	"""
	Calculates price variance for an item with currency conversion.

	Args:
		pi_item: Purchase Invoice Item
		pr_item_data: Purchase Receipt Item data
		doc: Purchase Invoice document

	Returns:
		dict: Variance data
	"""
	# Get exchange rate from PI
	exchange_rate = flt(doc.conversion_rate) or 1.0
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	# Calculate rate difference
	rate_diff = flt(pi_item.rate) - flt(pr_item_data.rate)
	qty = flt(pi_item.qty)

	# Variance in transaction currency
	variance_transaction = rate_diff * qty

	# Convert to company currency if needed
	if doc.currency == company_currency:
		variance_company = variance_transaction
	else:
		# If PI is in foreign currency (e.g., UZS), convert to company currency (USD)
		variance_company = variance_transaction / exchange_rate

	return {
		'pi_item': pi_item,
		'pr_item_name': pr_item_data.name,
		'item_code': pi_item.item_code,
		'item_name': pi_item.item_name,
		'pr_rate': pr_item_data.rate,
		'pi_rate': pi_item.rate,
		'qty': qty,
		'rate_diff': rate_diff,
		'variance_transaction': variance_transaction,
		'variance_company_currency': variance_company,
		'exchange_rate': exchange_rate,
		'transaction_currency': doc.currency,
		'company_currency': company_currency
	}


# ==================== LCV CREATION ====================

def create_lcv_for_pr_group(doc, pr_name, pr_group_data):
	"""
	Creates a Landed Cost Voucher for one PR group.

	Args:
		doc: Purchase Invoice document
		pr_name: Purchase Receipt name
		pr_group_data: Group data with items and variance

	Returns:
		object: Created LCV document
	"""
	pr_doc = pr_group_data['pr_doc']
	items = pr_group_data['items']
	total_variance = pr_group_data['total_variance']
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	# Create LCV
	lcv = frappe.new_doc("Landed Cost Voucher")
	lcv.company = doc.company
	lcv.posting_date = doc.posting_date or nowdate()

	# Add Purchase Receipt
	lcv.append("purchase_receipts", {
		"receipt_document_type": "Purchase Receipt",
		"receipt_document": pr_name,
		"supplier": pr_doc.supplier,
		"grand_total": pr_doc.grand_total
	})

	# Get variance account
	variance_account = get_price_variance_account(doc.company)

	# Add charge (total variance in company currency)
	lcv.append("taxes", {
		"description": f"Price Variance from PI {doc.name} (Auto-generated)",
		"expense_account": variance_account,
		"amount": total_variance
	})

	# Save and get items
	lcv.flags.ignore_permissions = True
	lcv.insert()
	lcv.get_items_from_purchase_receipts()

	# Apply item-specific distribution (Yo'l A: Aniq distribute)
	apply_item_specific_distribution(lcv, items, total_variance)

	# Validate and submit
	lcv.validate()
	lcv.save()
	lcv.submit()

	return lcv


def apply_item_specific_distribution(lcv, variance_items, total_variance):
	"""
	Distributes variance only to items that have price differences.
	(Yo'l A: Aniq Distribution)

	Args:
		lcv: Landed Cost Voucher document
		variance_items: List of items with variance
		total_variance: Total variance amount
	"""
	# Create mapping: pr_item_name -> variance_amount
	variance_map = {
		item['pr_item_name']: item['variance_company_currency']
		for item in variance_items
	}

	# Apply to LCV items
	for lcv_item in lcv.items:
		if lcv_item.purchase_receipt_item in variance_map:
			# Set applicable charges for this specific item
			lcv_item.applicable_charges = variance_map[lcv_item.purchase_receipt_item]
		else:
			# No variance for this item
			lcv_item.applicable_charges = 0.0


# ==================== ACCOUNT HELPER ====================

def get_price_variance_account(company):
	"""
	Finds or returns appropriate price variance expense account.

	Args:
		company: Company name

	Returns:
		str: Account name
	"""
	abbr = frappe.get_cached_value("Company", company, "abbr")

	# 1. Try standard "Stock Variance" or "Price Variance" account
	possible_names = [
		f"Price Variance - {abbr}",
		f"Purchase Price Variance - {abbr}",
		f"Stock Variance - {abbr}",
		f"Cost Variance - {abbr}"
	]

	for account_name in possible_names:
		if frappe.db.exists("Account", account_name):
			return account_name

	# 2. Search for accounts with variance keywords
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
		if any(word in acc_lower for word in ["variance", "price", "difference", "narx", "farq"]):
			return acc.name

	# 3. Use company default expense account
	default_account = frappe.db.get_value("Company", company, "default_expense_account")
	if default_account:
		return default_account

	# 4. Use first available expense account
	if accounts:
		return accounts[0].name

	# 5. Throw error if nothing found
	frappe.throw(
		_("Price Variance uchun expense account topilmadi! Iltimos, account yarating yoki company default ni sozlang.")
	)


# ==================== LCV REFERENCE MANAGEMENT ====================

def save_lcv_references(doc, lcv_list):
	"""
	Saves LCV references to PI custom field.

	Args:
		doc: Purchase Invoice document
		lcv_list: List of created LCV documents
	"""
	if not lcv_list:
		return

	lcv_names = [lcv.name for lcv in lcv_list]

	# Save as JSON in custom field
	frappe.db.set_value(
		"Purchase Invoice",
		doc.name,
		"custom_price_variance_lcvs",
		json.dumps(lcv_names),
		update_modified=False
	)


def get_lcv_references(doc):
	"""
	Gets linked LCV references from PI.

	Args:
		doc: Purchase Invoice document

	Returns:
		list: LCV names
	"""
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
	"""
	Clears LCV references from PI.

	Args:
		doc: Purchase Invoice document
	"""
	frappe.db.set_value(
		"Purchase Invoice",
		doc.name,
		"custom_price_variance_lcvs",
		None,
		update_modified=False
	)


# ==================== USER INTERFACE ====================

def show_success_message(doc, pr_groups, created_lcvs):
	"""
	Shows detailed success message to user.

	Args:
		doc: Purchase Invoice document
		pr_groups: PR groups with variance data
		created_lcvs: List of created LCV documents
	"""
	company_currency = frappe.get_cached_value('Company', doc.company, 'default_currency')

	# Build items table
	items_html = ""
	grand_total_variance = 0.0

	for pr_name, pr_data in pr_groups.items():
		items_html += f"""
		<tr style='background: #f8f9fa; font-weight: bold;'>
			<td colspan='6' style='padding: 8px;'>
				📦 Purchase Receipt: {pr_name}
			</td>
		</tr>
		"""

		for item in pr_data['items']:
			color = "red" if item['variance_company_currency'] > 0 else "green"

			items_html += f"""
			<tr>
				<td style='padding: 5px;'>{item['item_code']}</td>
				<td style='padding: 5px;'>{item['item_name'][:30]}</td>
				<td style='padding: 5px; text-align: right;'>{item['pr_rate']:.4f}</td>
				<td style='padding: 5px; text-align: right;'>{item['pi_rate']:.4f}</td>
				<td style='padding: 5px; text-align: right;'>{item['qty']:.2f}</td>
				<td style='padding: 5px; text-align: right; color: {color};'>
					{item['variance_company_currency']:,.2f} {company_currency}
				</td>
			</tr>
			"""

		grand_total_variance += pr_data['total_variance']

	# Build LCV links
	lcv_links = ""
	for lcv in created_lcvs:
		lcv_links += f"""
		<li>
			<a href='/app/landed-cost-voucher/{lcv.name}' target='_blank'
			   style='color: #155724; font-weight: bold;'>
				{lcv.name}
			</a>
		</li>
		"""

	# Show message
	frappe.msgprint(
		f"""
		<div style='padding: 15px; background: #fff3cd; border-left: 4px solid #ffc107;'>
			<h4 style='margin-top: 0; color: #856404;'>
				📊 Narx Farqi Aniqlandi - LCV Yaratildi
			</h4>
			<p><b>Item tannarxlari avtomatik yangilandi!</b></p>

			<table style='width: 100%; margin: 10px 0; border-collapse: collapse; font-size: 12px;'>
				<thead style='background: #e9ecef;'>
					<tr>
						<th style='padding: 8px; text-align: left;'>Item Code</th>
						<th style='padding: 8px; text-align: left;'>Item Name</th>
						<th style='padding: 8px; text-align: right;'>PR Rate</th>
						<th style='padding: 8px; text-align: right;'>PI Rate</th>
						<th style='padding: 8px; text-align: right;'>Qty</th>
						<th style='padding: 8px; text-align: right;'>Variance</th>
					</tr>
				</thead>
				<tbody>
					{items_html}
				</tbody>
				<tfoot style='background: #e9ecef; font-weight: bold;'>
					<tr>
						<td colspan='5' style='padding: 8px; text-align: right;'>JAMI FARQ:</td>
						<td style='padding: 8px; text-align: right; color: {"red" if grand_total_variance > 0 else "green"};'>
							{grand_total_variance:,.2f} {company_currency}
						</td>
					</tr>
				</tfoot>
			</table>

			<div style='margin-top: 15px; padding: 10px; background: #d4edda; border-left: 3px solid #28a745;'>
				<p style='margin: 0;'><b>✅ Yaratilgan LCV lar ({len(created_lcvs)} ta):</b></p>
				<ul style='margin: 5px 0;'>
					{lcv_links}
				</ul>
				<p style='margin: 5px 0 0 0;'><small>
					LCV itemlarning tannarxini yangiladi. Stock operatsiyalar yangi narxda bajariladi.
				</small></p>
			</div>
		</div>
		""",
		title=_("Item Tannarxlari Yangilandi"),
		indicator="orange",
		alert=True,
		wide=True
	)
