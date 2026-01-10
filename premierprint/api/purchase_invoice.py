# -*- coding: utf-8 -*-
# Copyright (c) 2026, Munisa and contributors
# For license information, please see license.txt

import frappe
from frappe import _


@frappe.whitelist()
def get_original_prices(items):
	"""
	Purchase Order yoki Purchase Receipt dan asl narxlarni olish.
	
	Args:
		items: List of dicts with {item_code, purchase_order, purchase_receipt, po_detail, pr_detail}
	
	Returns:
		Dict mapping "item_code_detail" -> original_rate
	"""
	import json
	if isinstance(items, str):
		items = json.loads(items)
	
	result = {}
	
	for item in items:
		item_code = item.get('item_code')
		po_detail = item.get('po_detail')
		pr_detail = item.get('pr_detail')
		purchase_order = item.get('purchase_order')
		purchase_receipt = item.get('purchase_receipt')
		
		original_rate = None
		key = f"{item_code}_{po_detail or pr_detail or ''}"
		
		# 1. Avval PO Item dan narxni olishga harakat qilamiz
		if po_detail:
			original_rate = frappe.db.get_value('Purchase Order Item', po_detail, 'rate')
		
		# 2. Agar PO Item topilmasa, PR Item dan olishga harakat qilamiz
		if original_rate is None and pr_detail:
			original_rate = frappe.db.get_value('Purchase Receipt Item', pr_detail, 'rate')
		
		# 3. Agar hali ham topilmasa, PO dan item_code bo'yicha qidiramiz
		if original_rate is None and purchase_order:
			original_rate = frappe.db.get_value(
				'Purchase Order Item',
				{'parent': purchase_order, 'item_code': item_code},
				'rate'
			)
		
		# 4. Oxirgi urinish - PR dan item_code bo'yicha
		if original_rate is None and purchase_receipt:
			original_rate = frappe.db.get_value(
				'Purchase Receipt Item',
				{'parent': purchase_receipt, 'item_code': item_code},
				'rate'
			)
		
		if original_rate is not None:
			result[key] = float(original_rate)
	
	return result
