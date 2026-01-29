import frappe
from frappe.model.document import Document
from frappe import _

class Asosiypanel(Document):
    def validate(self):
        # Validations
        if self.operation_type in ['production', 'usluga_po_zakasu']:
            if not self.finished_good:
                frappe.throw(_("Finished Good is required for Production"))
            if not self.production_qty or self.production_qty <= 0:
                frappe.throw(_("Production Qty must be greater than 0"))
        
        if self.operation_type in ['production', 'rasxod_po_zakasu', 'usluga_po_zakasu']:
            if not self.sales_order:
                frappe.throw(_("Sales Order is required for this operation type"))

    def on_submit(self):
        if self.operation_type == 'delivery_note':
            self.create_delivery_note()
        elif self.operation_type == 'material_transfer':
            self.create_stock_entry('Material Transfer')
        elif self.operation_type == 'material_issue':
            self.create_stock_entry('Material Issue')
        elif self.operation_type == 'purchase_request':
            self.create_material_request()
        elif self.operation_type == 'service_sale':
            self.create_sales_invoice()
        elif self.operation_type in ['production', 'usluga_po_zakasu']:
            self.create_production_entry()
        elif self.operation_type == 'rasxod_po_zakasu':
            self.create_material_issue_for_order()

    def create_production_entry(self):
        """Create Stock Entry (Repack) for Production/Usluga operations.
        
        This merges rasxod (Material Issue) and usluga (Service Costs) logic into ONE Repack entry:
        - Stock items → Consumption rows (s_warehouse set, t_warehouse None)
        - Non-stock items → Additional Costs table (adds service value to finished good)
        - Finished Good → Production row (s_warehouse None, t_warehouse set)
        """
        self.validate_stock()
        
        se = frappe.new_doc('Stock Entry')
        se.stock_entry_type = 'Repack'
        se.purpose = 'Repack'
        se.company = self.company
        se.from_warehouse = self.from_warehouse
        se.to_warehouse = self.to_warehouse
        
        # Link to Sales Order
        if self.sales_order:
            se.sales_order = self.sales_order

        total_service_cost = 0
        
        for item in self.items:
            # Use stored is_stock_item from child row (fetched by JS on item selection)
            is_stock = item.is_stock_item if hasattr(item, 'is_stock_item') and item.is_stock_item is not None else frappe.db.get_value("Item", item.item_code, "is_stock_item")
            
            if is_stock:
                # Consumption: Stock items go to items table (rasxod logic)
                se.append('items', {
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'qty': item.qty,
                    'uom': item.uom,
                    's_warehouse': self.from_warehouse,
                    't_warehouse': None
                })
            else:
                # Service items: Sum up the amount for additional_costs (usluga logic)
                total_service_cost += (item.amount or 0)
        
        # Add all service costs as a single additional_cost entry
        if total_service_cost > 0:
            se.append('additional_costs', {
                'expense_account': frappe.db.get_value("Company", self.company, "stock_adjustment_account"),
                'description': _("Service Costs from Asosiy Panel"),
                'amount': total_service_cost
            })
        
        # Production: Add finished good row
        se.append('items', {
            'item_code': self.finished_good,
            'qty': self.production_qty,
            't_warehouse': self.to_warehouse,
            's_warehouse': None,
            'is_finished_item': 1
        })
        
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        # User feedback with link
        frappe.msgprint(
            _("Production Stock Entry <a href='/app/stock-entry/{0}'>{0}</a> created successfully").format(se.name),
            indicator='green',
            alert=True
        )
        
        self.add_comment('Info', _('Production Stock Entry {0} created').format(
            f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'
        ))

    def create_material_issue_for_order(self):
        """Create Stock Entry (Material Issue) linked to Sales Order.
        
        Used for rasxod_po_zakasu operation - issues raw materials against a Sales Order.
        """
        self.validate_stock()
        
        se = frappe.new_doc('Stock Entry')
        se.stock_entry_type = 'Material Issue'
        se.purpose = 'Material Issue'
        se.company = self.company
        se.from_warehouse = self.from_warehouse
        
        # Link to Sales Order
        if self.sales_order:
            se.sales_order = self.sales_order
        
        for item in self.items:
            se.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                's_warehouse': self.from_warehouse,
                't_warehouse': None
            })
            
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        # User feedback with link
        frappe.msgprint(
            _("Material Issue <a href='/app/stock-entry/{0}'>{0}</a> created for Sales Order {1}").format(se.name, self.sales_order),
            indicator='green',
            alert=True
        )
        
        self.add_comment('Info', _('Material Issue {0} created for Sales Order {1}').format(
            f'<a href="/app/stock-entry/{se.name}">{se.name}</a>',
            self.sales_order
        ))

    def create_delivery_note(self):
        self.validate_stock()
        dn = frappe.new_doc('Delivery Note')
        dn.customer = self.customer
        dn.company = self.company
        dn.currency = self.currency
        dn.selling_price_list = self.price_list
        dn.set_warehouse = self.from_warehouse
        
        for item in self.items:
            dn.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                'rate': item.rate,
                'warehouse': self.from_warehouse
            })
            
        dn.flags.ignore_permissions = True
        dn.insert()
        dn.submit()
        self.add_comment('Info', _('Delivery Note {0} created').format(
            f'<a href="/app/delivery-note/{dn.name}">{dn.name}</a>'
        ))
        
        # Internal Transfer Logic
        if self.target_company and self.target_warehouse:
            self.create_inter_company_purchase_receipt(dn)

    def create_inter_company_purchase_receipt(self, dn):
        target_company = self.target_company
        # Find Supplier in Target Company that represents Source Company
        supplier_name = frappe.db.get_value("Supplier", {"represents_company": self.company}, "name")
        
        if not supplier_name:
             frappe.throw(_("Please setup a Supplier in {0} that represents {1}").format(target_company, self.company))

        pr = frappe.new_doc('Purchase Receipt')
        pr.company = target_company
        pr.supplier = supplier_name
        pr.set_warehouse = self.target_warehouse
        pr.currency = self.currency 
        pr.posting_date = self.posting_date
        
        for item in dn.items:
            pr.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                'rate': item.rate,
                'warehouse': self.target_warehouse
            })
            
        pr.flags.ignore_permissions = True
        pr.insert()
        # pr.submit() # Saving as Draft
        
        self.add_comment('Info', _('Purchase Receipt (Draft) {0} created in {1}').format(
            f'<a href="/app/purchase-receipt/{pr.name}">{pr.name}</a>', target_company
        ))

    def create_stock_entry(self, purpose):
        if purpose == 'Material Issue':
             self.validate_stock()
        
        se = frappe.new_doc('Stock Entry')
        se.purpose = purpose
        se.company = self.company
        se.from_warehouse = self.from_warehouse
        if purpose == 'Material Transfer':
            se.to_warehouse = self.to_warehouse
            if not se.to_warehouse:
                frappe.throw(_("To Warehouse is required for Material Transfer"))
        
        for item in self.items:
            se.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                's_warehouse': self.from_warehouse if purpose in ['Material Transfer', 'Material Issue'] else None,
                't_warehouse': self.to_warehouse if purpose == 'Material Transfer' else None
            })
            
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        self.add_comment('Info', _('Stock Entry {0} created').format(
             f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'
        ))

    def create_material_request(self):
        mr = frappe.new_doc('Material Request')
        mr.material_request_type = 'Purchase'
        mr.company = self.company
        
        for item in self.items:
            mr.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                'rate': item.rate,
                'warehouse': self.from_warehouse,
                'schedule_date': self.payment_due_date or frappe.utils.nowdate()
            })
            
        mr.flags.ignore_permissions = True
        mr.insert()
        mr.submit()
        self.add_comment('Info', _('Material Request {0} created').format(
            f'<a href="/app/material-request/{mr.name}">{mr.name}</a>'
        ))
        
    def create_sales_invoice(self):
        si = frappe.new_doc('Sales Invoice')
        si.customer = self.customer
        si.company = self.company
        si.currency = self.currency
        si.selling_price_list = self.price_list
        si.due_date = self.payment_due_date
        
        for item in self.items:
            si.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                'rate': item.rate
            })
            
        si.flags.ignore_permissions = True
        si.insert()
        si.submit()
        self.add_comment('Info', _('Sales Invoice {0} created').format(
            f'<a href="/app/sales-invoice/{si.name}">{si.name}</a>'
        ))

    def validate_stock(self):
        if self.from_warehouse:
            for item in self.items:
                 # Only check stock availability for stock items
                 if frappe.db.get_value("Item", item.item_code, "is_stock_item"):
                     actual_qty = frappe.db.get_value("Bin", {"item_code": item.item_code, "warehouse": self.from_warehouse}, "actual_qty") or 0
                     if actual_qty < item.qty:
                         frappe.throw(_("Insufficient stock for Item {0} in Warehouse {1}. Available: {2}, Required: {3}").format(item.item_code, self.from_warehouse, actual_qty, item.qty))