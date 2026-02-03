import frappe
from frappe.model.document import Document
from frappe import _

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
        
        # Inter-Company Price List validation for delivery_note
        if self.operation_type == 'delivery_note' and self.customer:
            self._validate_inter_company_price_list()

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
        elif self.operation_type == 'purchase_request':
            self.create_material_request()
        elif self.operation_type == 'service_sale':
            self.create_sales_invoice()
        elif self.operation_type == 'rasxod_po_zakasu':
            self.create_rasxod_material_transfer()
        elif self.operation_type == 'usluga_po_zakasu':
            self.log_service_cost()
        elif self.operation_type == 'production':
            self.create_aggregated_production_entry()

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
        
        # Link to Sales Order for aggregation tracking
        if self.sales_order:
            se.sales_order = self.sales_order
        
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
        
        This is the core of the Unified Production Hub. It:
        1. Finds all materials in WIP warehouse linked to this Sales Order Item
        2. Finds all service costs from submitted usluga_po_zakasu records
        3. Creates a Repack Stock Entry that:
           - Consumes materials from WIP
           - Adds service costs to additional_costs
           - Produces the finished good
        """
        # Step 1: Find materials in WIP warehouse for this Sales Order
        wip_materials = self._get_wip_materials_for_production()
        
        if not wip_materials:
            frappe.throw(
                _("No materials found in WIP warehouse for Sales Order {0}. Please create 'Rasxod po zakasu' entries first.").format(self.sales_order),
                title=_("No Materials Found")
            )
        
        # Step 2: Find all service costs for this Sales Order Item
        service_costs = self._get_service_costs_for_production()
        total_service_cost = sum(sc.get('total_amount', 0) for sc in service_costs)
        
        # Step 3: Create the Repack Stock Entry
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
        
        # Add consumption rows (materials from WIP)
        for material in wip_materials:
            se.append('items', {
                'item_code': material.get('item_code'),
                'item_name': material.get('item_name'),
                'qty': material.get('qty'),
                'uom': material.get('uom') or frappe.db.get_value("Item", material.get('item_code'), "stock_uom"),
                's_warehouse': self.from_warehouse,  # WIP warehouse
                't_warehouse': None  # CRITICAL: Must be None for consumption
            })
        
        # Add service costs to additional_costs table
        if total_service_cost > 0:
            expense_account = frappe.db.get_value("Company", self.company, "stock_adjustment_account")
            if not expense_account:
                frappe.throw(_("Please set Stock Adjustment Account in Company {0}").format(self.company))
            
            se.append('additional_costs', {
                'expense_account': expense_account,
                'description': _("Service Costs from Usluga po zakasu (Total: {0} entries)").format(len(service_costs)),
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
        mr = frappe.new_doc('Material Request')
        mr.material_request_type = 'Purchase'
        mr.company = self.company
        mr.transaction_date = self.posting_date
        
        # Set default supplier if provided (for RFQ/PO generation)
        # Note: Material Request doesn't have a direct supplier field,
        # but we can add it to remarks for reference
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            mr.custom_remarks = _("Preferred Supplier: {0}").format(supplier_name)
        
        for item in self.items:
            item_dict = {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom,
                'rate': item.rate,
                'warehouse': self.from_warehouse,
                'schedule_date': self.payment_due_date or frappe.utils.nowdate()
            }
            mr.append('items', item_dict)
            
        mr.flags.ignore_permissions = True
        mr.insert()
        mr.submit()
        
        # Include supplier in success message if provided
        supplier_msg = ""
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            supplier_msg = _(" (Preferred Supplier: {0})").format(supplier_name)
        
        self.add_comment('Info', _('Material Request {0} created{1}').format(
            f'<a href="/app/material-request/{mr.name}">{mr.name}</a>',
            supplier_msg
        ))
        
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