import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import nowdate

class Asosiypanel(Document):
    def validate(self):
        """Validate document before saving."""
        # Validations for production operations
        if self.operation_type == 'production':
            if not self.finished_good:
                frappe.throw(_("Finished Good is required for Production"))
            if not self.production_qty or self.production_qty <= 0:
                frappe.throw(_("Production Qty must be greater than 0"))
            if not self.from_warehouse:
                frappe.throw(_("From Warehouse (WIP) is required for Production"))
            if not self.to_warehouse:
                frappe.throw(_("To Warehouse (Finished Goods Store) is required for Production"))
        
        # Validations for usluga_po_zakasu (service logging)
        if self.operation_type == 'usluga_po_zakasu':
            if not self.finished_good:
                frappe.throw(_("Finished Good is required for Service Order"))
            if not self.production_qty or self.production_qty <= 0:
                frappe.throw(_("Production Qty must be greater than 0"))
            # Validate all items are service items (non-stock)
            self._validate_service_items()
        
        # Validations for rasxod_po_zakasu (material transfer to WIP)
        if self.operation_type == 'rasxod_po_zakasu':
            if not self.from_warehouse:
                frappe.throw(_("From Warehouse (Main Store) is required for Rasxod"))
            if not self.to_warehouse:
                frappe.throw(_("To Warehouse (WIP) is required for Rasxod"))
        
        # Sales Order is required for all 3 production-related operations
        if self.operation_type in ['production', 'rasxod_po_zakasu', 'usluga_po_zakasu']:
            if not self.sales_order:
                frappe.throw(_("Sales Order is required for this operation type"))

        if self.operation_type == "material_request":
            self._validate_material_request()

        if self.operation_type == "purchase_receipt":
            self._validate_purchase_receipt()
        
        # Inter-Company Price List validation for delivery_note
        if self.operation_type == 'delivery_note' and self.customer:
            self._validate_inter_company_price_list()

    def _validate_material_request(self):
        if not self.from_warehouse:
            frappe.throw(_("From Warehouse (Requesting Warehouse) is required for Material Request"))
        if not self.items or len(self.items) == 0:
            frappe.throw(_("Items table is empty. Please add at least one item."))

        for row in self.items:
            if not row.item_code:
                frappe.throw(_("Item Code is required in items table"))
            if not frappe.db.exists("Item", row.item_code):
                frappe.throw(_("Item {0} does not exist in Item master").format(row.item_code))
            if not row.qty or row.qty <= 0:
                frappe.throw(_("Qty must be greater than 0 for Item {0}").format(row.item_code))

    def _validate_purchase_receipt(self):
        if not self.supplier:
            frappe.throw(_("Supplier is required for Purchase Receipt"))
        if not self.items or len(self.items) == 0:
            frappe.throw(_("Items table is empty. Please add at least one item."))

        for row in self.items:
            if not row.item_code:
                frappe.throw(_("Item Code is required in items table"))
            if not frappe.db.exists("Item", row.item_code):
                frappe.throw(_("Item {0} does not exist in Item master").format(row.item_code))
            if not row.qty or row.qty <= 0:
                frappe.throw(_("Qty must be greater than 0 for Item {0}").format(row.item_code))

            is_stock_item = frappe.db.get_value("Item", row.item_code, "is_stock_item")
            if is_stock_item:
                row_warehouse = getattr(row, "warehouse", None) or self.from_warehouse
                if not row_warehouse:
                    frappe.throw(_("Warehouse is required for stock Item {0}").format(row.item_code))

    def _validate_service_items(self):
        """Validate that all items in usluga_po_zakasu are service items (non-stock)."""
        for item in self.items:
            is_stock = item.is_stock_item if hasattr(item, 'is_stock_item') and item.is_stock_item is not None else frappe.db.get_value("Item", item.item_code, "is_stock_item")
            if is_stock:
                frappe.throw(
                    _("Item {0} is a stock item. Only service items (non-stock) are allowed in 'Usluga po zakasu' operation.").format(item.item_code),
                    title=_("Invalid Item Type")
                )

    def _validate_inter_company_price_list(self):
        """Validate Inter-Company Price List for internal customer transactions.
        
        Ensures that when delivering to an internal customer, the correct
        'Inter-Company Price List' is used for consistent accounting.
        """
        INTER_COMPANY_PRICE_LIST = "Inter-Company Price List"
        
        # Check if customer is internal
        is_internal = frappe.db.get_value("Customer", self.customer, "is_internal_customer")
        
        if is_internal:
            # Check if Inter-Company Price List exists
            if not frappe.db.exists("Price List", INTER_COMPANY_PRICE_LIST):
                frappe.throw(
                    _("Inter-Company Price List topilmadi. Iltimos, '{0}' nomli Price List yarating va 'Buying' hamda 'Selling' opsiyalarini yoqing.").format(INTER_COMPANY_PRICE_LIST),
                    title=_("Price List Xatosi"),
                    exc=frappe.ValidationError
                )
            
            # Validate that the correct price list is selected
            if self.price_list != INTER_COMPANY_PRICE_LIST:
                frappe.throw(
                    _("Ichki mijoz ({0}) uchun faqat '{1}' ishlatilishi kerak. Joriy tanlov: '{2}'").format(
                        self.customer, INTER_COMPANY_PRICE_LIST, self.price_list or "Bo'sh"
                    ),
                    title=_("Noto'g'ri Price List"),
                    exc=frappe.ValidationError
                )

    def on_submit(self):
        """Handle document submission based on operation type."""
        if self.operation_type == 'delivery_note':
            self.create_delivery_note()
        elif self.operation_type == 'material_transfer':
            self.create_stock_entry('Material Transfer')
        elif self.operation_type == 'material_issue':
            self.create_stock_entry('Material Issue')
        elif self.operation_type == 'material_request':
            self.create_material_request()
        elif self.operation_type == 'service_sale':
            self.create_sales_invoice()
        elif self.operation_type == 'rasxod_po_zakasu':
            self.create_rasxod_material_transfer()
        elif self.operation_type == 'usluga_po_zakasu':
            self.log_service_cost()
        elif self.operation_type == 'production':
            self.create_aggregated_production_entry()
        elif self.operation_type == 'purchase_receipt':
            self.make_purchase_receipt()

    def create_rasxod_material_transfer(self):
        """Create Stock Entry (Material Transfer) for rasxod_po_zakasu operation.
        
        Transfers raw materials from Main Store to WIP warehouse.
        This entry is linked to Sales Order Item for later aggregation in Production.
        """
        self.validate_stock()
        
        se = frappe.new_doc('Stock Entry')
        se.stock_entry_type = 'Material Transfer'
        se.purpose = 'Material Transfer'
        se.company = self.company
        se.posting_date = self.posting_date
        se.from_warehouse = self.from_warehouse
        se.to_warehouse = self.to_warehouse
        
        # Link to Sales Order for aggregation tracking (using custom fields)
        if self.sales_order:
            se.custom_sales_order = self.sales_order
        if self.sales_order_item:
            se.custom_sales_order_item = self.sales_order_item
        
        # Add supplier reference to remarks if provided
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            se.remarks = _("Supplier: {0} | Asosiy Panel: {1}").format(supplier_name, self.name)
        
        for item in self.items:
            se.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom or frappe.db.get_value("Item", item.item_code, "stock_uom"),
                's_warehouse': self.from_warehouse,
                't_warehouse': self.to_warehouse
            })
        
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        # Store the Stock Entry name for reference
        frappe.msgprint(
            _("Material Transfer <a href='/app/stock-entry/{0}'>{0}</a> created. Materials moved to WIP warehouse.").format(se.name),
            indicator='green',
            alert=True
        )
        
        self.add_comment('Info', _('Rasxod (Material Transfer) {0} created for Sales Order {1}').format(
            f'<a href="/app/stock-entry/{se.name}">{se.name}</a>',
            self.sales_order
        ))

    def log_service_cost(self):
        """Log service costs for usluga_po_zakasu operation.
        
        NO Stock Entry is created. This record serves as a data log 
        for future production aggregation. All service costs will be 
        added to the Production Stock Entry's additional_costs table.
        """
        # Calculate total service cost
        total_service_cost = sum(item.amount or 0 for item in self.items)
        
        # Include supplier info in message if provided
        supplier_info = ""
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            supplier_info = _(" from Supplier: {0}").format(supplier_name)
        
        frappe.msgprint(
            _("Service costs of {0} logged for Sales Order {1}, Item {2}{3}. No stock movement created.").format(
                frappe.format_value(total_service_cost, {'fieldtype': 'Currency'}),
                self.sales_order,
                self.finished_good,
                supplier_info
            ),
            indicator='blue',
            alert=True
        )
        
        self.add_comment('Info', _('Service Cost Log: {0} for finished good {1}{2}').format(
            frappe.format_value(total_service_cost, {'fieldtype': 'Currency'}),
            self.finished_good,
            supplier_info
        ))

    def create_aggregated_production_entry(self):
        """Create Stock Entry (Repack) for production operation - The Aggregator.
        
        This is the core of the Unified Production Hub. It uses items from the table:
        - Items with is_wip_item=1 → Consumption rows (materials from WIP)
        - Items with is_wip_item=0 AND is_stock_item=0 → Additional costs (services)
        - Finished good → Production row
        
        The items table is auto-populated by frontend when sales_order_item is selected.
        """
        # Validate items table
        if not self.items or len(self.items) == 0:
            frappe.throw(
                _("No items found in the table. Please select Sales Order Item to auto-fetch materials and services."),
                title=_("No Items")
            )
        
        # Separate WIP materials from services using is_wip_item flag
        wip_materials = [item for item in self.items if item.is_wip_item]
        service_items = [item for item in self.items if not item.is_wip_item and not item.is_stock_item]
        
        if not wip_materials:
            frappe.throw(
                _("No WIP materials found. Please ensure 'Rasxod po zakasu' entries exist for this Sales Order."),
                title=_("No Materials")
            )
        
        # Calculate total service cost
        total_service_cost = sum((item.amount or 0) for item in service_items)
        
        # Create the Repack Stock Entry
        se = frappe.new_doc('Stock Entry')
        se.stock_entry_type = 'Repack'
        se.purpose = 'Repack'
        se.company = self.company
        se.posting_date = self.posting_date
        
        # Link to Sales Order
        if self.sales_order:
            se.sales_order = self.sales_order
        
        # Add supplier reference to remarks if provided
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            se.remarks = _("Production for SO: {0} | Supplier: {1} | Asosiy Panel: {2}").format(
                self.sales_order, supplier_name, self.name
            )
        
        # Add consumption rows (WIP materials - is_wip_item=1)
        for item in wip_materials:
            uom = item.uom or frappe.db.get_value("Item", item.item_code, "stock_uom")
            se.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': uom,
                's_warehouse': self.from_warehouse,  # WIP warehouse
                't_warehouse': None  # CRITICAL: Must be None for consumption
            })
        
        # Add service costs to additional_costs table (is_wip_item=0, is_stock_item=0)
        if total_service_cost > 0:
            expense_account = frappe.db.get_value("Company", self.company, "stock_adjustment_account")
            if not expense_account:
                frappe.throw(_("Please set Stock Adjustment Account in Company {0}").format(self.company))
            
            se.append('additional_costs', {
                'expense_account': expense_account,
                'description': _("Service Costs from Usluga po zakasu ({0} items, Total: {1})").format(
                    len(service_items),
                    frappe.format_value(total_service_cost, {'fieldtype': 'Currency'})
                ),
                'amount': total_service_cost
            })
        
        # Add finished good production row
        finished_uom = frappe.db.get_value("Item", self.finished_good, "stock_uom")
        se.append('items', {
            'item_code': self.finished_good,
            'qty': self.production_qty,
            'uom': finished_uom,
            's_warehouse': None,  # CRITICAL: Must be None for production
            't_warehouse': self.to_warehouse,  # Finished goods warehouse
            'is_finished_item': 1
        })
        
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        # Detailed user feedback
        frappe.msgprint(
            _("Production Stock Entry <a href='/app/stock-entry/{0}'>{0}</a> created successfully.<br>"
              "Materials consumed: {1} items<br>"
              "Service costs added: {2}<br>"
              "Finished good: {3} x {4}").format(
                se.name,
                len(wip_materials),
                frappe.format_value(total_service_cost, {'fieldtype': 'Currency'}),
                self.finished_good,
                self.production_qty
            ),
            indicator='green',
            alert=True
        )
        
        self.add_comment('Info', _('Production Stock Entry {0} created with {1} materials and {2} service cost').format(
            f'<a href="/app/stock-entry/{se.name}">{se.name}</a>',
            len(wip_materials),
            frappe.format_value(total_service_cost, {'fieldtype': 'Currency'})
        ))

    def _get_wip_materials_for_production(self):
        """Query materials currently in WIP warehouse for this Sales Order.
        
        Finds all Stock Entry items that:
        - Were transferred TO the WIP warehouse (from_warehouse in current doc)
        - Are linked to the same Sales Order
        - Stock Entry is submitted (docstatus = 1)
        
        Returns:
            list: List of dicts with item_code, item_name, qty, uom
        """
        # Get materials from rasxod_po_zakasu Stock Entries
        materials = frappe.db.sql("""
            SELECT 
                sei.item_code,
                sei.item_name,
                SUM(sei.qty) as qty,
                sei.uom
            FROM `tabStock Entry Item` sei
            INNER JOIN `tabStock Entry` se ON sei.parent = se.name
            WHERE se.docstatus = 1
                AND se.sales_order = %(sales_order)s
                AND sei.t_warehouse = %(wip_warehouse)s
                AND se.purpose = 'Material Transfer'
            GROUP BY sei.item_code, sei.item_name, sei.uom
        """, {
            'sales_order': self.sales_order,
            'wip_warehouse': self.from_warehouse  # WIP warehouse is source for production
        }, as_dict=True)
        
        return materials

    def _get_service_costs_for_production(self):
        """Query all service costs logged for this Sales Order Item.
        
        Finds all submitted Asosiy panel records of type 'usluga_po_zakasu'
        that are linked to the same Sales Order and (optionally) Sales Order Item.
        
        Returns:
            list: List of dicts with name, total_amount
        """
        # Build filter based on sales_order_item if available
        filters = {
            'docstatus': 1,
            'operation_type': 'usluga_po_zakasu',
            'sales_order': self.sales_order
        }
        
        if self.sales_order_item:
            filters['sales_order_item'] = self.sales_order_item
        
        if self.finished_good:
            filters['finished_good'] = self.finished_good
        
        service_records = frappe.get_all(
            'Asosiy panel',
            filters=filters,
            fields=['name', 'total_amount']
        )
        
        return service_records

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
        se.posting_date = self.posting_date
        se.from_warehouse = self.from_warehouse
        se.to_warehouse = self.to_warehouse
        
        # Link to Sales Order
        if self.sales_order:
            se.sales_order = self.sales_order

        total_service_cost = 0
        
        for item in self.items:
            # Use stored is_stock_item from child row (fetched by JS on item selection)
            is_stock = item.is_stock_item if hasattr(item, 'is_stock_item') and item.is_stock_item is not None else frappe.db.get_value("Item", item.item_code, "is_stock_item")
            
            # Get UOM if not set
            uom = item.uom if item.uom else frappe.db.get_value("Item", item.item_code, "stock_uom")
            
            if is_stock:
                # Consumption: Stock items go to items table (rasxod logic)
                se.append('items', {
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'qty': item.qty,
                    'uom': uom,
                    's_warehouse': self.from_warehouse,
                    't_warehouse': None  # CRITICAL: Must be None for consumption
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
        finished_uom = frappe.db.get_value("Item", self.finished_good, "stock_uom")
        se.append('items', {
            'item_code': self.finished_good,
            'qty': self.production_qty,
            'uom': finished_uom,
            't_warehouse': self.to_warehouse,
            's_warehouse': None,  # CRITICAL: Must be None for production
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

    def create_delivery_note(self):
        """Create Delivery Note and handle 2-stage Inter-Company automation.
        
        STAGE 1 (This method):
        1. Source Company: Delivery Note (DN) - Submit
        2. Target Company: Purchase Receipt (PR) - DRAFT (manual checkpoint)
        
        STAGE 2 (via hooks.py - Purchase Receipt on_submit):
        3. Target Company: Purchase Invoice (PI) - Auto-submit when PR is submitted
        """
        self.validate_stock()
        
        # Check if customer is internal
        is_internal = frappe.db.get_value("Customer", self.customer, "is_internal_customer")
        
        # ============================================================
        # STEP 1: Create and Submit Delivery Note (Source Company)
        # ============================================================
        dn = frappe.new_doc('Delivery Note')
        dn.customer = self.customer
        dn.company = self.company
        dn.posting_date = self.posting_date
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
        
        self.add_comment('Info', _('1. Delivery Note {0} created and submitted').format(
            f'<a href="/app/delivery-note/{dn.name}">{dn.name}</a>'
        ))
        
        # ============================================================
        # INTERNAL CUSTOMER: 2-Stage Inter-Company Automation
        # ============================================================
        if is_internal and self.target_company and self.target_warehouse:
            try:
                # STAGE 1, STEP 2: Create Purchase Receipt as DRAFT in Target Company
                pr = self._create_purchase_receipt_from_dn(dn)
                
                # Success message - inform user about next steps
                frappe.msgprint(
                    _("<b>STAGE 1 Complete!</b><br><br>"
                      "<b>Source Company ({0}):</b><br>"
                      "• Delivery Note: <a href='/app/delivery-note/{1}'>{1}</a> ✅ Submitted<br><br>"
                      "<b>Target Company ({2}):</b><br>"
                      "• Purchase Receipt: <a href='/app/purchase-receipt/{3}'>{3}</a> 📝 Draft<br><br>"
                      "<hr>"
                      "<b>Keyingi qadam:</b> Purchase Receipt ni ko'rib chiqing va submit qiling. "
                      "Purchase Invoice avtomatik yaratiladi.").format(
                        self.company, dn.name,
                        self.target_company, pr.name
                    ),
                    indicator='blue',
                    title=_("Inter-Company: Manual Checkpoint")
                )
                
            except Exception as e:
                frappe.log_error(
                    title=_("Inter-Company Transaction Error"),
                    message=frappe.get_traceback()
                )
                frappe.throw(
                    _("Error in Inter-Company automation: {0}").format(str(e)),
                    title=_("Transaction Failed")
                )
        else:
            # Non-internal customer - just show DN created
            frappe.msgprint(
                _("Delivery Note <a href='/app/delivery-note/{0}'>{0}</a> created and submitted").format(dn.name),
                indicator='green',
                alert=True
            )

    def _create_purchase_receipt_from_dn(self, dn):
        """Create Purchase Receipt in Target Company as DRAFT.
        
        STAGE 1: Creates PR as draft for manual review.
        STAGE 2: When user submits PR, Purchase Invoice is auto-created via hooks.
        
        Maps items from DN to PR with correct warehouse mapping.
        """
        # Find Supplier in Target Company that represents Source Company
        supplier_name = frappe.db.get_value(
            "Supplier", 
            {"represents_company": self.company, "is_internal_supplier": 1}, 
            "name"
        )
        
        if not supplier_name:
            frappe.throw(
                _("Please setup an Internal Supplier in {0} that represents {1}").format(
                    self.target_company, self.company
                )
            )
        
        pr = frappe.new_doc('Purchase Receipt')
        pr.company = self.target_company
        pr.supplier = supplier_name
        pr.posting_date = self.posting_date
        pr.currency = self.currency
        pr.set_warehouse = self.target_warehouse
        
        # Map items from DN
        for dn_item in dn.items:
            pr.append('items', {
                'item_code': dn_item.item_code,
                'item_name': dn_item.item_name,
                'qty': dn_item.qty,
                'uom': dn_item.uom,
                'rate': dn_item.rate,
                'warehouse': self.target_warehouse,
                'received_qty': dn_item.qty
            })
        
        pr.flags.ignore_permissions = True
        pr.insert()
        # DO NOT SUBMIT - Leave as Draft for manual review (STAGE 2)
        # pr.submit()
        
        self.add_comment('Info', _('2. Purchase Receipt {0} created as DRAFT (Target Company: {1}). Please review and submit manually.').format(
            f'<a href="/app/purchase-receipt/{pr.name}">{pr.name}</a>',
            self.target_company
        ))
        
        return pr

    def create_stock_entry(self, purpose):
        if purpose == 'Material Issue':
             self.validate_stock()
        
        se = frappe.new_doc('Stock Entry')
        se.purpose = purpose
        se.stock_entry_type = purpose # Mapping type strictly to purpose for these cases
        se.company = self.company
        se.posting_date = self.posting_date
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
        """Create and submit ERPNext Material Request for material_request."""
        self._validate_material_request()

        try:
            mr_doc = frappe.new_doc("Material Request")
            mr_doc.material_request_type = "Purchase"
            mr_doc.transaction_date = self.posting_date
            mr_doc.company = self.company

            # Minimal audit trail
            if hasattr(mr_doc, "remarks"):
                mr_doc.remarks = _("Created from Asosiy panel {0}").format(self.name)

            schedule_date = self.posting_date or nowdate()

            for row in self.items:
                mr_doc.append(
                    "items",
                    {
                        "item_code": row.item_code,
                        "qty": row.qty,
                        "uom": row.uom,
                        "warehouse": self.from_warehouse,
                        "schedule_date": schedule_date,
                    },
                )

            mr_doc.insert(ignore_permissions=True)
            mr_doc.submit()

            mr_link = f"<a href='/app/material-request/{mr_doc.name}'>{mr_doc.name}</a>"
            frappe.msgprint(
                _("Material Request {0} created and submitted").format(mr_link),
                indicator="green",
                alert=True,
            )

            self.add_comment("Info", _("Material Request {0} created").format(mr_link))

            try:
                ap_link = f"<a href='/app/asosiy-panel/{self.name}'>{self.name}</a>"
                mr_doc.add_comment("Info", _("Created from Asosiy panel {0}").format(ap_link))
            except Exception:
                pass

        except Exception:
            frappe.log_error(frappe.get_traceback(), _("Asosiy panel → Material Request failed"))
            frappe.throw(_("Failed to create Material Request. Please check Error Log."))

    def make_purchase_receipt(self):
        """Create and submit ERPNext Purchase Receipt for purchase_receipt."""
        self._validate_purchase_receipt()

        try:
            pr_doc = frappe.new_doc("Purchase Receipt")
            pr_doc.supplier = self.supplier
            pr_doc.company = self.company
            pr_doc.posting_date = self.posting_date

            if hasattr(pr_doc, "currency") and self.currency:
                pr_doc.currency = self.currency

            # Map price list if relevant in your setup (optional field)
            if hasattr(pr_doc, "buying_price_list") and self.price_list:
                pr_doc.buying_price_list = self.price_list

            if hasattr(pr_doc, "set_warehouse") and self.from_warehouse:
                pr_doc.set_warehouse = self.from_warehouse

            for row in self.items:
                pr_doc.append(
                    "items",
                    {
                        "item_code": row.item_code,
                        "qty": row.qty,
                        "uom": row.uom,
                        "rate": getattr(row, "rate", None),
                        "warehouse": self.from_warehouse,
                    },
                )

            pr_doc.insert(ignore_permissions=True)
            pr_doc.submit()

            pr_link = f"<a href='/app/purchase-receipt/{pr_doc.name}'>{pr_doc.name}</a>"
            frappe.msgprint(
                _("Purchase Receipt {0} created and submitted").format(pr_link),
                indicator="green",
                alert=True,
            )

            self.add_comment("Info", _("Purchase Receipt {0} created").format(pr_link))

            try:
                ap_link = f"<a href='/app/asosiy-panel/{self.name}'>{self.name}</a>"
                pr_doc.add_comment("Info", _("Created from Asosiy panel {0}").format(ap_link))
            except Exception:
                pass

        except Exception:
            frappe.log_error(frappe.get_traceback(), _("Asosiy panel → Purchase Receipt failed"))
            frappe.throw(_("Failed to create Purchase Receipt. Please check Error Log."))
        
    def create_sales_invoice(self):
        si = frappe.new_doc('Sales Invoice')
        si.customer = self.customer
        si.company = self.company
        si.currency = self.currency
        si.selling_price_list = self.price_list
        si.posting_date = self.posting_date
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

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_so_items(doctype, txt, searchfield, start, page_len, filters):
    """Get Sales Order Items for a given Sales Order, bypassing permissions.
    
    This function is whitelisted to allow frontend queries without permission checks.
    Standard Frappe query function signature.
    """
    # Extract sales_order from filters
    import json
    if isinstance(filters, str):
        filters = json.loads(filters)
    
    sales_order = filters.get("sales_order") if filters else None
    
    if not sales_order:
        return []
    
    # Build search condition
    search_condition = ""
    if txt:
        search_condition = f"AND (soi.name LIKE %(txt)s OR soi.item_code LIKE %(txt)s OR soi.item_name LIKE %(txt)s)"
    
    # Query using SQL - return as list of tuples for Frappe compatibility
    # First column is the ID, second column is displayed as description
    return frappe.db.sql(f"""
        SELECT 
            soi.name,
            CONCAT(soi.item_code, ' - ', soi.item_name) as description
        FROM `tabSales Order Item` soi
        WHERE soi.parent = %(sales_order)s
        {search_condition}
        ORDER BY soi.idx
        LIMIT %(start)s, %(page_len)s
    """, {
        "sales_order": sales_order,
        "txt": f"%{txt}%",
        "start": start,
        "page_len": page_len
    })

@frappe.whitelist()
def get_item_details_from_so_item(so_item):
    """Fetch item_code from a Sales Order Item.
    
    This directly fetches from DB bypassing Permission Manager.
    
    Args:
        so_item: Name of the Sales Order Item
        
    Returns:
        str: item_code
    """
    if not so_item:
        return None
    
    # frappe.db.get_value bypasses permissions by default when called from whitelisted function
    item_code = frappe.db.get_value("Sales Order Item", so_item, "item_code")
    return item_code


@frappe.whitelist()
def get_production_data(sales_order, sales_order_item, wip_warehouse, finished_good=None):
    """Fetch materials from WIP and service costs for Production auto-fill.
    
    This function aggregates:
    1. Materials in WIP warehouse - from rasxod_po_zakasu Stock Entries
    2. Service costs - from usluga_po_zakasu Asosiy Panel records
    
    Args:
        sales_order: Sales Order name
        sales_order_item: Sales Order Item name
        wip_warehouse: WIP Warehouse to fetch materials from
        finished_good: (Optional) Finished Good item code for filtering services
        
    Returns:
        dict: {
            'materials': [...],   # WIP materials with is_wip_item=1
            'services': [...],    # Service items with is_wip_item=0
            'total_material_cost': float,
            'total_service_cost': float
        }
    """
    if not sales_order or not sales_order_item:
        frappe.throw(_("Sales Order and Sales Order Item are required"))
    
    # DEBUG: Log input parameters
    frappe.log_error(
        f"get_production_data called:\n"
        f"sales_order: {sales_order}\n"
        f"sales_order_item: {sales_order_item}\n"
        f"wip_warehouse: {wip_warehouse}\n"
        f"finished_good: {finished_good}",
        "Production Data Debug - Input"
    )
    
    # ========================================
    # PART 1: Fetch Materials from WIP Warehouse
    # ========================================
    # Find Stock Entry Items transferred to WIP via rasxod_po_zakasu
    # Using frappe.get_all for better site context handling
    
    # First get all submitted Stock Entries for this Sales Order with Material Transfer
    # Using custom_sales_order field (custom field added to Stock Entry)
    stock_entries = frappe.get_all(
        'Stock Entry',
        filters={
            'docstatus': 1,
            'custom_sales_order': sales_order,
            'purpose': 'Material Transfer'
        },
        fields=['name']
    )
    
    # DEBUG: Log stock entries found
    frappe.log_error(
        f"Stock Entries found: {len(stock_entries)}\n"
        f"Entries: {[se.name for se in stock_entries]}",
        "Production Data Debug - Stock Entries"
    )
    
    # Get items from these stock entries that were transferred to WIP warehouse
    materials = []
    material_map = {}  # For aggregating same items
    
    for se in stock_entries:
        items = frappe.get_all(
            'Stock Entry Detail',
            filters={
                'parent': se.name,
                't_warehouse': wip_warehouse
            },
            fields=['item_code', 'item_name', 'qty', 'uom', 'valuation_rate']
        )
        
        for item in items:
            key = (item.item_code, item.uom)
            if key in material_map:
                # Aggregate quantity and average rate
                existing = material_map[key]
                total_qty = existing['qty'] + item.qty
                # Weighted average rate
                existing['rate'] = ((existing['qty'] * existing['rate']) + (item.qty * (item.valuation_rate or 0))) / total_qty if total_qty else 0
                existing['qty'] = total_qty
            else:
                material_map[key] = {
                    'item_code': item.item_code,
                    'item_name': item.item_name,
                    'qty': item.qty,
                    'uom': item.uom,
                    'rate': item.valuation_rate or 0,
                    'is_stock_item': 1,
                    'is_wip_item': 1
                }
    
    materials = list(material_map.values())
    
    # Calculate total material cost
    total_material_cost = 0
    for mat in materials:
        mat['amount'] = (mat.get('qty') or 0) * (mat.get('rate') or 0)
        total_material_cost += mat['amount']
    
    # ========================================
    # PART 2: Fetch Service Costs from usluga_po_zakasu
    # ========================================
    # Build filters for service records
    service_filters = {
        'docstatus': 1,
        'operation_type': 'usluga_po_zakasu',
        'sales_order': sales_order,
        'sales_order_item': sales_order_item
    }
    
    if finished_good:
        service_filters['finished_good'] = finished_good
    
    # Get all usluga_po_zakasu records
    service_records = frappe.get_all(
        'Asosiy panel',
        filters=service_filters,
        fields=['name']
    )
    
    # Get service items from child tables
    services = []
    total_service_cost = 0
    
    for sr in service_records:
        service_items = frappe.get_all(
            'Asosiy panel item',
            filters={'parent': sr.name},
            fields=['item_code', 'item_name', 'qty', 'uom', 'rate', 'amount']
        )
        for si in service_items:
            si['is_stock_item'] = 0
            si['is_wip_item'] = 0  # Service items are NOT WIP items
            si['source_record'] = sr.name
            services.append(si)
            total_service_cost += si.get('amount') or 0
    
    return {
        'materials': materials,
        'services': services,
        'total_material_cost': total_material_cost,
        'total_service_cost': total_service_cost
    }