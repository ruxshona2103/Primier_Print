import frappe
from frappe.model.document import Document
from frappe import _
from frappe.utils import nowdate, flt

# Operation Type Mapping (Russian → DocType Purpose)
TYPE_MAP = {
    "Запрос материалов": "Material Request",
    "Приход на склад": "Purchase Receipt",
    "Списание материалов": "Material Issue",
    "Перемещения": "Material Transfer",
    "Отгрузка товаров": "Delivery Note",
    "Расход по заказу": "Rasxod Material Transfer",
    "Услуги по заказу": "Service Cost Log",
    "Производство": "Production Repack",
}

PURCHASE_RECEIPT_OPERATION = "Приход на склад"


def normalize_operation_type(value):
    return (value or "").strip().replace("A", "А").replace("a", "а")

class Asosiypanel(Document):
    def validate(self):
        """Validate document before saving."""
        operation_type = normalize_operation_type(self.operation_type)

        # Validations for production operations
        if operation_type == 'Производство':
            if not self.finished_good:
                frappe.throw(_("Finished Good is required for Production"))
            if not self.production_qty or self.production_qty <= 0:
                frappe.throw(_("Production Qty must be greater than 0"))
            if not self.from_warehouse:
                frappe.throw(_("From Warehouse (WIP) is required for Production"))
            if not self.to_warehouse:
                frappe.throw(_("To Warehouse (Finished Goods Store) is required for Production"))
        
        # Validations for usluga_po_zakasu (service logging)
        if operation_type == 'Услуги по заказу':
            if not self.supplier:
                frappe.throw(_("Supplier is required for Service Order operations"))
            if not self.finished_good:
                frappe.throw(_("Finished Good is required for Service Order"))
            if not self.production_qty or self.production_qty <= 0:
                frappe.throw(_("Production Qty must be greater than 0"))
            # Validate all items are service items (non-stock)
            self._validate_service_items()
            # Multi-currency validation
            self._validate_currency_and_exchange_rate()
        
        # Validations for rasxod_po_zakasu (material transfer to WIP)
        if operation_type == 'Расход по заказу':
            if not self.from_warehouse:
                frappe.throw(_("From Warehouse (Main Store) is required for Rasxod"))
            if not self.to_warehouse:
                frappe.throw(_("To Warehouse (WIP) is required for Rasxod"))
        
        # Sales Order is required for all 3 production-related operations
        if operation_type in ['Производство', 'Расход по заказу', 'Услуги по заказу']:
            if not self.sales_order:
                frappe.throw(_("Sales Order is required for this operation type"))

        if operation_type == "Запрос материалов":
            self._validate_material_request()

        if operation_type == PURCHASE_RECEIPT_OPERATION:
            self._validate_purchase_receipt()
        
        # Inter-Company Price List validation for delivery_note
        if operation_type == 'Отгрузка товаров' and self.customer:
            self._validate_inter_company_price_list()

    def before_save(self):
        operation_type = normalize_operation_type(self.operation_type)
        if operation_type != PURCHASE_RECEIPT_OPERATION:
            return

        if self.supplier:
            return

        if self.is_new():
            return

        previous_supplier = frappe.db.get_value(self.doctype, self.name, "supplier")
        if previous_supplier:
            self.supplier = previous_supplier

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
    
    def _validate_currency_and_exchange_rate(self):
        """Validate currency and exchange rate for multi-currency transactions.
        
        Uses safe attribute access to prevent AttributeError if fields
        are not yet synced in the DocType metadata.
        """
        currency = getattr(self, 'currency', None)
        exchange_rate = flt(getattr(self, 'exchange_rate', None))
        
        if not currency:
            # If currency field doesn't exist or is empty, skip validation
            return
        
        # Get company's base currency
        company_currency = frappe.db.get_value("Company", self.company, "default_currency")
        
        # If foreign currency, ensure exchange rate is valid
        if currency != company_currency:
            if exchange_rate <= 0:
                frappe.throw(
                    _("Exchange Rate must be greater than 0 for foreign currency transactions. Currency: {0}, Company Currency: {1}").format(
                        currency, company_currency
                    ),
                    title=_("Invalid Exchange Rate")
                )
        else:
            # If same currency, force exchange rate to 1
            if exchange_rate != 1.0:
                try:
                    self.exchange_rate = 1.0
                except AttributeError:
                    pass  # Field doesn't exist yet in metadata

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
        if self.operation_type == 'Отгрузка товаров':
            self.create_delivery_note()
        elif self.operation_type == 'Перемещения':
            self.create_stock_entry('Material Transfer')
        elif self.operation_type == 'Списание материалов':
            self.create_stock_entry('Material Issue')
        elif self.operation_type == 'Запрос материалов':
            self.create_material_request()
        elif self.operation_type == 'service_sale':
            self.create_sales_invoice()
        elif self.operation_type == 'Расход по заказу':
            self.create_rasxod_material_transfer()
        elif self.operation_type == 'Услуги по заказу':
            self.log_service_cost()
        elif self.operation_type == 'Производство':
            self.create_aggregated_production_entry()
        elif self.operation_type == 'Приход на склад':
            self.make_purchase_receipt()

    def _store_linked_doc(self, doctype, docname, secondary=False):
        """Store linked document reference for cancellation tracking.
        
        Args:
            doctype: DocType of the linked document
            docname: Name of the linked document
            secondary: If True, store in the secondary pair (for inter-company 2nd doc)
        """
        if secondary:
            frappe.db.set_value(self.doctype, self.name, {
                'linked_document_type_2': doctype,
                'linked_document_name_2': docname
            }, update_modified=False)
        else:
            frappe.db.set_value(self.doctype, self.name, {
                'linked_document_type': doctype,
                'linked_document_name': docname
            }, update_modified=False)

    def on_cancel(self):
        """Recursive Cancellation Chain for Asosiy panel.
        
        When this document is cancelled, ALL background documents created by it
        must be automatically and safely cancelled to prevent "Ghost Entries"
        in the Stock Ledger and General Ledger.
        
        Strategy:
        1. Cancel explicitly tracked linked documents (reverse order: secondary → primary)
        2. Deep scan all possible DocTypes for any documents referencing self.name
        3. Cancel all found submitted documents with proper error handling
        4. Report results to the user
        """
        cancelled_docs = []

        # =====================================================================
        # PHASE 1: Cancel explicitly tracked linked documents
        # Order: secondary first (e.g., inter-company PR), then primary (e.g., DN)
        # =====================================================================
        if self.linked_document_type_2 and self.linked_document_name_2:
            self._cancel_linked_doc(
                self.linked_document_type_2,
                self.linked_document_name_2,
                cancelled_docs
            )

        if self.linked_document_type and self.linked_document_name:
            self._cancel_linked_doc(
                self.linked_document_type,
                self.linked_document_name,
                cancelled_docs
            )

        # =====================================================================
        # PHASE 2: Deep scan — find ALL remaining linked documents by reference
        # This catches documents that may have been created outside the
        # _store_linked_doc tracking, preventing "Ghost Entries"
        # =====================================================================
        # Collect names already processed to avoid double-cancellation
        already_processed = set()
        for dt, dn in cancelled_docs:
            # Strip "(o'chirildi)" suffix from deleted drafts
            clean_name = dn.replace(" (o'chirildi)", "")
            already_processed.add((dt, clean_name))

        # Also add the tracked names even if cancellation failed above
        if self.linked_document_type and self.linked_document_name:
            already_processed.add((self.linked_document_type, self.linked_document_name))
        if self.linked_document_type_2 and self.linked_document_name_2:
            already_processed.add((self.linked_document_type_2, self.linked_document_name_2))

        # DocTypes to scan for orphaned references
        SCAN_DOCTYPES = [
            "Stock Entry",
            "Purchase Receipt",
            "Delivery Note",
            "Sales Invoice",
            "Purchase Invoice",
            "Material Request",
        ]

        for doctype in SCAN_DOCTYPES:
            found_docs = self._find_linked_docs_by_reference(doctype)

            for doc_name in found_docs:
                if (doctype, doc_name) in already_processed:
                    continue
                already_processed.add((doctype, doc_name))
                self._cancel_linked_doc(doctype, doc_name, cancelled_docs)

        # =====================================================================
        # PHASE 3: User feedback and audit trail
        # =====================================================================
        if cancelled_docs:
            doc_links = []
            for dt, dn in cancelled_docs:
                route = dt.lower().replace(' ', '-')
                clean_name = dn.replace(" (o'chirildi)", "")
                doc_links.append(
                    f"<a href='/app/{route}/{clean_name}'>{dt}: {dn}</a>"
                )
            frappe.msgprint(
                _("✅ Bekor qilingan hujjatlar:<br>{0}").format('<br>'.join(doc_links)),
                indicator='orange',
                alert=True
            )
        else:
            frappe.msgprint(
                _("ℹ️ Bog'langan hujjatlar topilmadi. Faqat Asosiy panel bekor qilindi."),
                indicator='blue',
                alert=True
            )

        self.add_comment('Info', _('Asosiy panel bekor qilindi. Bog\'langan hujjatlar: {0}').format(
            ', '.join([f'{dt} {dn}' for dt, dn in cancelled_docs]) or _('Yo\'q')
        ))

    def _find_linked_docs_by_reference(self, doctype):
        """Search for documents of a given DocType that reference this Asosiy panel.
        
        Searches across multiple reference fields:
        - remarks: Contains 'Asosiy Panel: <name>'
        - custom_asosiy_panel_ref: Direct link field (if exists)
        
        Args:
            doctype: The DocType to search in (e.g., 'Stock Entry')
            
        Returns:
            list: List of document names (docstatus == 1) linked to this panel
        """
        found = []

        # ------------------------------------------------------------------
        # Strategy 1: Search by `remarks` field (all creation methods embed
        #             "Asosiy Panel: {self.name}" in remarks)
        # ------------------------------------------------------------------
        meta = frappe.get_meta(doctype)
        if meta.has_field("remarks"):
            docs_by_remarks = frappe.get_all(
                doctype,
                filters={
                    "docstatus": 1,
                    "remarks": ["like", f"%{self.name}%"]
                },
                pluck="name",
                ignore_permissions=True
            )
            found.extend(docs_by_remarks)

        # ------------------------------------------------------------------
        # Strategy 2: Search by `custom_asosiy_panel_ref` (direct link field)
        # ------------------------------------------------------------------
        if meta.has_field("custom_asosiy_panel_ref"):
            docs_by_ref = frappe.get_all(
                doctype,
                filters={
                    "docstatus": 1,
                    "custom_asosiy_panel_ref": self.name
                },
                pluck="name",
                ignore_permissions=True
            )
            found.extend(docs_by_ref)

        # Return unique names
        return list(set(found))

    def _cancel_linked_doc(self, doctype, docname, cancelled_docs):
        """Cancel a single linked document with comprehensive error handling.
        
        Handles three states:
        - docstatus == 1 (Submitted): Cancel with ignore_permissions
        - docstatus == 0 (Draft): Delete with force
        - docstatus == 2 (Already Cancelled): Skip silently
        
        Args:
            doctype: DocType to cancel
            docname: Document name to cancel
            cancelled_docs: List to append (doctype, docname) tuples on success
        """
        if not frappe.db.exists(doctype, docname):
            frappe.msgprint(
                _("{0} {1} topilmadi (allaqachon o'chirilgan bo'lishi mumkin)").format(doctype, docname),
                indicator='yellow'
            )
            return

        doc = frappe.get_doc(doctype, docname)

        if doc.docstatus == 1:
            # Submitted → Cancel
            try:
                doc.flags.ignore_permissions = True
                doc.cancel()
                cancelled_docs.append((doctype, docname))
            except Exception as e:
                frappe.throw(
                    _("<b>{0} {1}</b> ni bekor qilib bo'lmadi:<br>{2}<br><br>"
                      "Bu hujjatga boshqa tranzaktsiyalar bog'langan bo'lishi mumkin.<br>"
                      "Iltimos, avval <b>shu hujjatga bog'langan</b> keyingi hujjatlarni "
                      "bekor qiling, so'ngra qayta urinib ko'ring.").format(
                        doctype, docname, str(e)
                    ),
                    title=_("Bekor qilish xatosi — bog'liqlik mavjud")
                )
        elif doc.docstatus == 0:
            # Draft → Delete
            try:
                doc.flags.ignore_permissions = True
                frappe.delete_doc(doctype, docname, force=True, ignore_permissions=True)
                cancelled_docs.append((doctype, f"{docname} (o'chirildi)"))
            except Exception as e:
                frappe.msgprint(
                    _("{0} {1} draft hujjatini o'chirib bo'lmadi: {2}").format(
                        doctype, docname, str(e)
                    ),
                    indicator='yellow'
                )
        # docstatus == 2 → Already cancelled, skip silently

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
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Stock Entry', se.name)
        
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
        """Create and submit Purchase Invoice for service costs.
        
        This ensures:
        1. Financial debt is recorded in Accounts Payable immediately
        2. Purchase Invoice Items are linked to sales_order and sales_order_item for production aggregation
        3. Multi-currency support with exchange rates
        """
        if not self.supplier:
            frappe.throw(_("Supplier is required for service cost operations"))
        
        # Create Purchase Invoice
        company_currency = frappe.db.get_value("Company", self.company, "default_currency")
        doc_currency = getattr(self, 'currency', None) or company_currency
        doc_exchange_rate = flt(getattr(self, 'exchange_rate', None)) or 1.0
        
        pi = frappe.new_doc('Purchase Invoice')
        pi.supplier = self.supplier
        pi.company = self.company
        pi.posting_date = self.posting_date
        pi.currency = doc_currency
        pi.conversion_rate = doc_exchange_rate
        pi.update_stock = 0  # CRITICAL: No stock update for service items
        
        # Add reference to Sales Order in remarks
        pi.remarks = _("Service costs for SO: {0}, Item: {1} | Asosiy Panel: {2}").format(
            self.sales_order,
            self.finished_good,
            self.name
        )
        
        # Map items from Asosiy panel to Purchase Invoice
        for item in self.items:
            # Get expense account for service item
            expense_account = frappe.db.get_value("Item Default", 
                {"parent": item.item_code, "company": self.company}, 
                "expense_account"
            )
            if not expense_account:
                expense_account = frappe.db.get_value("Company", self.company, "default_expense_account")
            
            pi_item = pi.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': item.uom or frappe.db.get_value("Item", item.item_code, "stock_uom"),
                'rate': item.rate,
                'amount': item.amount,
                'expense_account': expense_account
            })
            
            # Store traceability in custom fields
            # Note: Assumes custom_sales_order and custom_sales_order_item fields exist on Purchase Invoice Item
            if hasattr(pi_item, 'custom_sales_order'):
                pi_item.custom_sales_order = self.sales_order
            if hasattr(pi_item, 'custom_sales_order_item'):
                pi_item.custom_sales_order_item = self.sales_order_item
            if hasattr(pi_item, 'custom_finished_good'):
                pi_item.custom_finished_good = self.finished_good
        
        # Insert and submit
        pi.flags.ignore_permissions = True
        pi.insert()
        pi.submit()
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Purchase Invoice', pi.name)
        
        # Calculate base amount for display
        total_amount = sum(flt(item.amount) for item in self.items)
        base_amount = total_amount * pi.conversion_rate
        
        # Build user message
        supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
        currency_info = ""
        if doc_currency != company_currency:
            currency_info = _(" ({0} {1} @ {2} = {3} {4})").format(
                frappe.format_value(total_amount, {'fieldtype': 'Currency'}),
                doc_currency,
                frappe.format_value(pi.conversion_rate, {'fieldtype': 'Float', 'precision': 6}),
                frappe.format_value(base_amount, {'fieldtype': 'Currency'}),
                company_currency
            )
        
        frappe.msgprint(
            _("Purchase Invoice <a href='/app/purchase-invoice/{0}'>{0}</a> created and submitted.<br>"
              "Supplier: {1}<br>"
              "Amount: {2} {3}{4}<br>"
              "Debt recorded in Accounts Payable.").format(
                pi.name,
                supplier_name,
                frappe.format_value(total_amount, {'fieldtype': 'Currency'}),
                doc_currency,
                currency_info
            ),
            indicator='green',
            alert=True
        )
        
        self.add_comment('Info', _('Purchase Invoice {0} created: {1} {2} (Base: {3} {4}) for SO {5}').format(
            f'<a href="/app/purchase-invoice/{pi.name}">{pi.name}</a>',
            frappe.format_value(total_amount, {'fieldtype': 'Currency'}),
            doc_currency,
            frappe.format_value(base_amount, {'fieldtype': 'Currency'}),
            company_currency,
            self.sales_order
        ))

    def create_aggregated_production_entry(self):
        """Create Stock Entry (Repack) for production operation - The Aggregator.
        
        This is the ADVANCED aggregator that:
        1. Consumes WIP materials (is_wip_material=1)
        2. Adds service costs from Purchase Invoices to additional_costs (is_wip_material=0)
        3. Produces finished goods
        4. Maintains full traceability to Purchase Invoices
        
        The items table is auto-populated by frontend via get_all_costs_for_production.
        """
        # ========================================
        # VALIDATION PHASE
        # ========================================
        if not self.items or len(self.items) == 0:
            frappe.throw(
                _("No items found in the table. Please select Sales Order Item to auto-fetch materials and services."),
                title=_("No Items")
            )
        
        # Separate WIP materials from services using is_wip_item flag
        wip_materials = [item for item in self.items if item.is_wip_item]
        service_items = [item for item in self.items if not item.is_wip_item and not item.is_stock_item]
        
        # CRITICAL VALIDATION: Ensure at least materials OR services exist
        if not wip_materials and not service_items:
            frappe.throw(
                _("No materials or services found for Sales Order Item: {0}.<br><br>"
                  "Cannot create production without costs. Please ensure:<br>"
                  "1. 'Расход по заказу' (Material Transfer to WIP) entries exist, OR<br>"
                  "2. 'Услуги по заказу' (Service Cost) Purchase Invoices are submitted").format(
                    self.sales_order_item or "Not Selected"
                ),
                title=_("No Production Costs Found")
            )
        
        # Warning if only materials (no services)
        if not service_items and wip_materials:
            frappe.msgprint(
                _("⚠️ No service costs found. Production will use materials only."),
                indicator='orange',
                alert=True
            )
        
        # Warning if only services (no materials) - unusual but allowed
        if not wip_materials and service_items:
            frappe.msgprint(
                _("⚠️ No WIP materials found. Production will use service costs only (pure service production)."),
                indicator='orange',
                alert=True
            )
        
        # ========================================
        # STOCK ENTRY CREATION
        # ========================================
        se = frappe.new_doc('Stock Entry')
        se.stock_entry_type = 'Repack'
        se.purpose = 'Repack'
        se.company = self.company
        se.posting_date = self.posting_date
        
        # Link to Sales Order for traceability
        if self.sales_order:
            se.sales_order = self.sales_order
        
        # Build comprehensive remarks with Purchase Invoice traceability
        remarks_parts = [_("Production for Sales Order: {0}").format(self.sales_order)]
        remarks_parts.append(_("Sales Order Item: {0}").format(self.sales_order_item))
        remarks_parts.append(_("Finished Good: {0} x {1}").format(self.finished_good, self.production_qty))
        
        # Collect Purchase Invoices from service items for audit trail
        purchase_invoices = set()
        for si in service_items:
            # Extract PI from source_reference or item_name
            if hasattr(si, 'source_reference') and si.source_reference:
                purchase_invoices.add(si.source_reference)
        
        if purchase_invoices:
            remarks_parts.append(_("Service Purchase Invoices: {0}").format(', '.join(sorted(purchase_invoices))))
        
        if self.supplier:
            supplier_name = frappe.db.get_value("Supplier", self.supplier, "supplier_name") or self.supplier
            remarks_parts.append(_("Reference Supplier: {0}").format(supplier_name))
        
        remarks_parts.append(_("Asosiy Panel: {0}").format(self.name))
        se.remarks = ' | '.join(remarks_parts)
        
        # ========================================
        # PART 1: Material Consumption (WIP → Consumed)
        # ========================================
        for item in wip_materials:
            uom = item.uom or frappe.db.get_value("Item", item.item_code, "stock_uom")
            se.append('items', {
                'item_code': item.item_code,
                'item_name': item.item_name,
                'qty': item.qty,
                'uom': uom,
                's_warehouse': self.from_warehouse,  # WIP warehouse (source)
                't_warehouse': None  # CRITICAL: None = Consumed
            })
        
        # ========================================
        # PART 2: Service Costs Aggregation (Additional Costs)
        # ========================================
        total_service_cost = sum((item.amount or 0) for item in service_items)
        
        if total_service_cost > 0:
            # Get default expense account
            default_expense_account = frappe.db.get_value("Company", self.company, "stock_adjustment_account")
            if not default_expense_account:
                frappe.throw(_("Please set Stock Adjustment Account in Company {0}").format(self.company))
            
            # Group service costs by expense account for proper accounting
            expense_by_account = {}
            for si in service_items:
                # Get expense account from item (if fetched from PI) or use default
                account = getattr(si, 'expense_account', None) or default_expense_account
                
                if account not in expense_by_account:
                    expense_by_account[account] = {
                        'amount': 0,
                        'items': [],
                        'pi_references': set()
                    }
                
                expense_by_account[account]['amount'] += flt(si.get('amount') or 0)
                expense_by_account[account]['items'].append(si.get('item_code'))
                
                # Track PI reference for this service
                if hasattr(si, 'source_reference') and si.source_reference:
                    expense_by_account[account]['pi_references'].add(si.source_reference)
            
            # Add each expense account to additional_costs table
            for account, data in expense_by_account.items():
                description_parts = []
                description_parts.append(_("Service Costs: {0}").format(
                    ', '.join(data['items'][:3]) + ('...' if len(data['items']) > 3 else '')
                ))
                if data['pi_references']:
                    description_parts.append(_("PI: {0}").format(', '.join(sorted(data['pi_references']))))
                
                se.append('additional_costs', {
                    'expense_account': account,
                    'description': ' | '.join(description_parts),
                    'amount': data['amount']
                })
        
        # ========================================
        # PART 3: Finished Good Production (→ Finished Goods Warehouse)
        # ========================================
        finished_uom = frappe.db.get_value("Item", self.finished_good, "stock_uom")
        se.append('items', {
            'item_code': self.finished_good,
            'qty': self.production_qty,
            'uom': finished_uom,
            's_warehouse': None,  # CRITICAL: None = Produced
            't_warehouse': self.to_warehouse,  # Finished goods warehouse
            'is_finished_item': 1
        })
        
        # ========================================
        # EXECUTION PHASE
        # ========================================
        se.flags.ignore_permissions = True
        se.insert()
        se.submit()
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Stock Entry', se.name)
        
        # ========================================
        # USER FEEDBACK WITH TRACEABILITY
        # ========================================
        company_currency = frappe.db.get_value("Company", self.company, "default_currency")
        
        # Build detailed feedback message
        msg_parts = []
        msg_parts.append(_("✅ Production Stock Entry <a href='/app/stock-entry/{0}'>{0}</a> created successfully.").format(se.name))
        msg_parts.append("<br><br><b>" + _("Production Summary:") + "</b>")
        
        if wip_materials:
            material_cost = sum((m.amount or 0) for m in wip_materials)
            msg_parts.append(_("📦 Materials consumed: {0} items ({1})").format(
                len(wip_materials),
                frappe.format_value(material_cost, {'fieldtype': 'Currency'}) + ' ' + company_currency
            ))
        
        if service_items:
            msg_parts.append(_("🔧 Service costs added: {0} items ({1})").format(
                len(service_items),
                frappe.format_value(total_service_cost, {'fieldtype': 'Currency'}) + ' ' + company_currency
            ))
            
            if purchase_invoices:
                msg_parts.append(_("💳 Purchase Invoices: {0}").format(
                    ', '.join([f'<a href="/app/purchase-invoice/{pi}">{pi}</a>' for pi in sorted(purchase_invoices)])
                ))
        
        msg_parts.append(_("🎁 Finished good: <b>{0}</b> x {1}").format(self.finished_good, self.production_qty))
        
        frappe.msgprint(
            '<br>'.join(msg_parts),
            indicator='green',
            alert=True
        )
        
        # Add comment with traceability
        comment_parts = [
            _('Production Stock Entry {0} created').format(f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'),
            _('Materials: {0}').format(len(wip_materials)),
            _('Services: {0} ({1})').format(
                len(service_items),
                frappe.format_value(total_service_cost, {'fieldtype': 'Currency'}) + ' ' + company_currency
            )
        ]
        if purchase_invoices:
            comment_parts.append(_('PIs: {0}').format(', '.join(sorted(purchase_invoices))))
        
        self.add_comment('Info', ' | '.join(comment_parts))

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
            'operation_type': 'Услуги по заказу',
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
        dn.currency = getattr(self, 'currency', None) or frappe.db.get_value('Company', self.company, 'default_currency')
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
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Delivery Note', dn.name)
        
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
        pr.currency = getattr(self, 'currency', None) or frappe.db.get_value('Company', self.target_company, 'default_currency')
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
        
        # Store as secondary linked doc for cancellation tracking
        self._store_linked_doc('Purchase Receipt', pr.name, secondary=True)
        
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
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Stock Entry', se.name)
        
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
                # Fetch Item Master details for proper UOM and conversion
                item_doc = frappe.get_cached_doc("Item", row.item_code)
                stock_uom = item_doc.stock_uom
                item_uom = row.uom or stock_uom
                
                # Calculate conversion factor
                conversion_factor = 1.0
                if item_uom != stock_uom:
                    uom_conversion = frappe.db.get_value(
                        "UOM Conversion Detail",
                        {"parent": row.item_code, "uom": item_uom},
                        "conversion_factor"
                    )
                    conversion_factor = flt(uom_conversion) if uom_conversion else 1.0

                mr_doc.append(
                    "items",
                    {
                        "item_code": row.item_code,
                        "qty": row.qty,
                        "uom": item_uom,
                        "stock_uom": stock_uom,
                        "conversion_factor": conversion_factor,
                        "warehouse": self.from_warehouse,
                        "schedule_date": schedule_date,
                    },
                )

            mr_doc.insert(ignore_permissions=True)
            mr_doc.submit()
            
            # Store reference for cancellation tracking
            self._store_linked_doc('Material Request', mr_doc.name)

            # Force status to "Pending" to ensure visibility in Purchase Order
            frappe.db.set_value("Material Request", mr_doc.name, "status", "Pending", update_modified=False)
            frappe.db.commit()

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
        """Create and submit ERPNext Purchase Receipt for purchase_receipt.
        
        CRITICAL: Maps purchase_order and purchase_order_item (po_detail) to each
        PR item so ERPNext updates received_qty on the original Purchase Order.
        """
        self._validate_purchase_receipt()

        try:
            pr_doc = frappe.new_doc("Purchase Receipt")
            pr_doc.supplier = self.supplier
            pr_doc.company = self.company
            pr_doc.posting_date = self.posting_date

            if hasattr(pr_doc, "currency") and getattr(self, 'currency', None):
                pr_doc.currency = self.currency

            # Sync exchange rate from Asosiy panel
            exchange_rate = flt(getattr(self, 'exchange_rate', None))
            if exchange_rate and exchange_rate > 0:
                pr_doc.conversion_rate = exchange_rate

            # Map price list if relevant in your setup (optional field)
            if hasattr(pr_doc, "buying_price_list") and self.price_list:
                pr_doc.buying_price_list = self.price_list

            if hasattr(pr_doc, "set_warehouse") and self.from_warehouse:
                pr_doc.set_warehouse = self.from_warehouse

            # Remarks for traceability and cancellation chain
            pr_doc.remarks = _("Created from Asosiy panel {0}").format(self.name)

            for row in self.items:
                pr_item = {
                    "item_code": row.item_code,
                    "qty": row.qty,
                    "uom": row.uom,
                    "rate": getattr(row, "rate", None),
                    "warehouse": self.from_warehouse,
                }

                # CRITICAL: Map PO reference so ERPNext updates received_qty
                if getattr(row, "purchase_order", None):
                    pr_item["purchase_order"] = row.purchase_order
                if getattr(row, "purchase_order_item", None):
                    pr_item["purchase_order_item"] = row.purchase_order_item

                pr_doc.append("items", pr_item)

            pr_doc.insert(ignore_permissions=True)
            pr_doc.submit()
            
            # Store reference for cancellation tracking
            self._store_linked_doc('Purchase Receipt', pr_doc.name)

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
        si.currency = getattr(self, 'currency', None) or frappe.db.get_value('Company', self.company, 'default_currency')
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
        
        # Store reference for cancellation tracking
        self._store_linked_doc('Sales Invoice', si.name)
        
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
    # PART 2: Fetch Service Costs from Purchase Invoice Items
    # ========================================
    # Find all submitted Purchase Invoice Items linked to this Sales Order Item
    # These were created by usluga_po_zakasu operations
    
    service_filters = {
        'docstatus': 1,
        'custom_sales_order': sales_order,
        'custom_sales_order_item': sales_order_item
    }
    
    if finished_good:
        service_filters['custom_finished_good'] = finished_good
    
    # Get Purchase Invoice Items with parent details for currency conversion
    service_items_data = frappe.db.sql("""
        SELECT 
            pii.item_code,
            pii.item_name,
            pii.qty,
            pii.uom,
            pii.rate,
            pii.amount as transaction_amount,
            pii.expense_account,
            pi.name as purchase_invoice,
            pi.currency,
            pi.conversion_rate
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE pi.docstatus = 1
            AND pii.custom_sales_order = %(sales_order)s
            AND pii.custom_sales_order_item = %(sales_order_item)s
            {finished_good_filter}
    """.format(
        finished_good_filter="AND pii.custom_finished_good = %(finished_good)s" if finished_good else ""
    ), {
        'sales_order': sales_order,
        'sales_order_item': sales_order_item,
        'finished_good': finished_good
    }, as_dict=True)
    
    # Convert to base currency and prepare service items
    services = []
    total_service_cost = 0  # In base currency
    
    for si in service_items_data:
        # Get conversion rate (exchange rate from Purchase Invoice)
        conversion_rate = flt(si.get('conversion_rate')) or 1.0
        transaction_amount = flt(si.get('transaction_amount') or 0)
        
        # Convert to base currency
        base_amount = transaction_amount * conversion_rate
        
        # Prepare service item for production
        service_item = {
            'item_code': si.item_code,
            'item_name': si.item_name,
            'qty': si.qty,
            'uom': si.uom,
            'rate': si.rate,
            'amount': base_amount,  # Use base amount for production costing
            'is_stock_item': 0,
            'is_wip_item': 0,
            'expense_account': si.expense_account,
            'source_record': si.purchase_invoice,
            'transaction_currency': si.currency,
            'conversion_rate': conversion_rate,
            'transaction_amount': transaction_amount
        }
        
        services.append(service_item)
        total_service_cost += base_amount  # Accumulate in base currency
    
    # DEBUG: Log service items found
    frappe.log_error(
        f"Service items found: {len(services)}\n"
        f"Total service cost (base currency): {total_service_cost}\n"
        f"Items: {[s['item_code'] for s in services]}",
        "Production Data Debug - Services"
    )
    
    return {
        'materials': materials,
        'services': services,
        'total_material_cost': total_material_cost,
        'total_service_cost': total_service_cost  # In base currency
    }


@frappe.whitelist()
def get_any_available_price(item_code, preferred_price_list, currency=None):
    """Get item price with fallback: preferred -> Standard Buying -> Standard Selling.

    Returns dict with 'rate' and 'source' (which price list the rate came from).
    """
    fallback_lists = [preferred_price_list, "Standard Buying", "Standard Selling"]
    # Remove duplicates while preserving order
    seen = set()
    price_lists = []
    for pl in fallback_lists:
        if pl and pl not in seen:
            seen.add(pl)
            price_lists.append(pl)

    for pl in price_lists:
        filters = {"item_code": item_code, "price_list": pl}
        if currency:
            filters["currency"] = currency
        rate = frappe.db.get_value("Item Price", filters, "price_list_rate")
        if rate and flt(rate) > 0:
            return {"rate": flt(rate), "source": pl}

    # Try again without currency filter as last resort
    if currency:
        for pl in price_lists:
            rate = frappe.db.get_value("Item Price", {
                "item_code": item_code,
                "price_list": pl,
            }, "price_list_rate")
            if rate and flt(rate) > 0:
                return {"rate": flt(rate), "source": pl}

    return {"rate": 0, "source": None}


@frappe.whitelist()
def get_items_from_purchase_orders(source_names):
    """Fetch PENDING items from selected Purchase Order(s) for Asosiy panel.
    
    For each PO item, calculates:
        pending_qty = flt(qty) - flt(received_qty)
    
    Only items with pending_qty > 0 are returned.
    Example: PO has 50 units, 20 already received → returns 30.
    """
    import json
    
    if isinstance(source_names, str):
        source_names = json.loads(source_names)
    
    if not isinstance(source_names, list):
        source_names = [source_names]
    
    if not source_names:
        frappe.throw(_("No Purchase Orders selected"))
    
    po_items = frappe.db.sql("""
        SELECT
            poi.item_code,
            poi.item_name,
            poi.qty,
            poi.received_qty,
            poi.uom,
            poi.stock_uom,
            poi.rate,
            poi.parent  AS purchase_order,
            poi.name    AS purchase_order_item
        FROM `tabPurchase Order Item` poi
        INNER JOIN `tabPurchase Order` po ON po.name = poi.parent
        WHERE po.docstatus = 1
          AND po.name IN %(names)s
        ORDER BY poi.parent, poi.idx
    """, {"names": source_names}, as_dict=True)
    
    items = []
    for row in po_items:
        pending_qty = flt(row.qty) - flt(row.received_qty)
        
        # Skip fully received items
        if pending_qty <= 0:
            continue
        
        rate = flt(row.rate)
        items.append({
            "item_code": row.item_code,
            "item_name": row.item_name,
            "qty": pending_qty,
            "uom": row.uom or row.stock_uom,
            "rate": rate,
            "amount": flt(pending_qty * rate),
            "purchase_order": row.purchase_order,
            "purchase_order_item": row.purchase_order_item,
        })
    
    return items


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_purchase_orders_for_selection(doctype, txt, searchfield, start, page_len, filters):
    """Custom query to fetch Purchase Orders with remaining item summary.
    
    Only shows POs where at least one item has remaining qty (qty - received_qty) > 0.
    """
    supplier = filters.get("supplier")
    company = filters.get("company")
    
    if not supplier or not company:
        return []
    
    query = """
        SELECT 
            po.name,
            po.supplier,
            po.transaction_date,
            po.grand_total,
            GROUP_CONCAT(
                DISTINCT CONCAT(
                    poi.item_name, 
                    ' (qoldiq: ', ROUND(poi.qty - poi.received_qty, 2), '/', ROUND(poi.qty, 2), ')'
                ) 
                ORDER BY poi.idx 
                SEPARATOR ', '
            ) as items_summary
        FROM 
            `tabPurchase Order` po
        INNER JOIN 
            `tabPurchase Order Item` poi ON poi.parent = po.name
                AND poi.qty > poi.received_qty
        WHERE 
            po.docstatus = 1
            AND po.supplier = %(supplier)s
            AND po.company = %(company)s
            AND po.status NOT IN ('Completed', 'Closed', 'Cancelled')
            AND (po.name LIKE %(txt)s OR po.supplier LIKE %(txt)s)
        GROUP BY 
            po.name
        HAVING
            SUM(poi.qty - poi.received_qty) > 0
        ORDER BY 
            po.transaction_date DESC
        LIMIT 
            %(start)s, %(page_len)s
    """
    
    return frappe.db.sql(
        query,
        {
            "supplier": supplier,
            "company": company,
            "txt": f"%{txt}%",
            "start": start,
            "page_len": page_len
        }
    )


@frappe.whitelist()
def get_purchase_order_meta(po_name):
    """Get currency and price list metadata from a Purchase Order.
    
    Used by JS to sync currency/exchange_rate/price_list when fetching items from PO.
    
    Returns:
        dict: {currency, buying_price_list, conversion_rate}
    """
    if not po_name:
        return {}
    
    meta = frappe.db.get_value(
        'Purchase Order', po_name,
        ['currency', 'buying_price_list', 'conversion_rate'],
        as_dict=True
    )
    
    return meta or {}


@frappe.whitelist()
def get_all_costs_for_production(sales_order_item, wip_warehouse, company=None):
    """Advanced aggregator: Fetch all materials and service costs for production.
    
    This method fetches:
    1. WIP Materials: From Stock Entry Details (materials transferred to WIP)
    2. Service Costs: From Purchase Invoice Items (submitted invoices linked to SO Item)
    
    Args:
        sales_order_item: Sales Order Item name to fetch costs for
        wip_warehouse: WIP Warehouse to fetch materials from
        company: Company name (for currency conversion)
        
    Returns:
        dict: {
            'materials': [...],  # WIP materials with is_wip_material=1
            'services': [...],   # Service items with is_wip_material=0
            'total_material_cost': float,
            'total_service_cost': float,
            'purchase_invoices': [...],  # List of PI names for traceability
            'has_data': bool
        }
    """
    if not sales_order_item:
        frappe.throw(_("Sales Order Item is required"))
    
    if not wip_warehouse:
        frappe.throw(_("WIP Warehouse is required"))
    
    # Get Sales Order from Sales Order Item
    sales_order = frappe.db.get_value('Sales Order Item', sales_order_item, 'parent')
    if not sales_order:
        frappe.throw(_("Sales Order Item {0} not found").format(sales_order_item))
    
    # Get company if not provided
    if not company:
        company = frappe.db.get_value('Sales Order', sales_order, 'company')
    
    company_currency = frappe.db.get_value('Company', company, 'default_currency')
    
    # ========================================
    # PART 1: Fetch WIP Materials
    # ========================================
    # Find all Stock Entry Details where:
    # - Items are transferred TO the WIP warehouse
    # - Linked to the Sales Order via custom_sales_order field
    # - Stock Entry is submitted
    
    materials_sql = """
        SELECT 
            sed.item_code,
            sed.item_name,
            SUM(sed.qty) as qty,
            sed.uom,
            AVG(sed.valuation_rate) as rate,
            SUM(sed.qty * sed.valuation_rate) as amount,
            sed.description,
            GROUP_CONCAT(DISTINCT se.name SEPARATOR ', ') as source_entries
        FROM `tabStock Entry Detail` sed
        INNER JOIN `tabStock Entry` se ON sed.parent = se.name
        WHERE se.docstatus = 1
            AND se.custom_sales_order = %(sales_order)s
            AND sed.t_warehouse = %(wip_warehouse)s
            AND se.purpose = 'Material Transfer'
        GROUP BY sed.item_code, sed.item_name, sed.uom, sed.description
        ORDER BY sed.item_code
    """
    
    materials_data = frappe.db.sql(materials_sql, {
        'sales_order': sales_order,
        'wip_warehouse': wip_warehouse
    }, as_dict=True)
    
    # Prepare materials list with flags
    materials = []
    total_material_cost = 0
    
    for mat in materials_data:
        material = {
            'item_code': mat.item_code,
            'item_name': mat.item_name,
            'qty': flt(mat.qty),
            'uom': mat.uom,
            'rate': flt(mat.rate),
            'amount': flt(mat.amount),
            'description': mat.description or mat.item_name,
            'is_wip_material': 1,  # Flag: This is a WIP material
            'is_stock_item': 1,
            'source_reference': mat.source_entries
        }
        materials.append(material)
        total_material_cost += material['amount']
    
    # ========================================
    # PART 2: Fetch Service Costs from Purchase Invoices
    # ========================================
    # Find all submitted Purchase Invoice Items linked to this Sales Order Item
    
    services_sql = """
        SELECT 
            pii.item_code,
            pii.item_name,
            pii.qty,
            pii.uom,
            pii.rate,
            pii.amount as transaction_amount,
            pii.base_amount,
            pii.expense_account,
            pii.description,
            pi.name as purchase_invoice,
            pi.supplier,
            pi.currency,
            pi.conversion_rate,
            pi.posting_date
        FROM `tabPurchase Invoice Item` pii
        INNER JOIN `tabPurchase Invoice` pi ON pii.parent = pi.name
        WHERE pi.docstatus = 1
            AND pii.custom_sales_order = %(sales_order)s
            AND pii.custom_sales_order_item = %(sales_order_item)s
            AND pi.update_stock = 0
        ORDER BY pi.posting_date, pi.name
    """
    
    services_data = frappe.db.sql(services_sql, {
        'sales_order': sales_order,
        'sales_order_item': sales_order_item
    }, as_dict=True)
    
    # Prepare services list with flags
    services = []
    total_service_cost = 0  # In base currency
    purchase_invoices = set()
    
    for svc in services_data:
        # Use base_amount (already converted to company currency)
        base_amount = flt(svc.base_amount or (svc.transaction_amount * flt(svc.conversion_rate or 1.0)))
        
        service = {
            'item_code': svc.item_code,
            'item_name': svc.item_name,
            'qty': flt(svc.qty),
            'uom': svc.uom,
            'rate': flt(svc.rate),
            'amount': base_amount,  # Use base amount for costing
            'description': _("Service: {0} (PI: {1}, Supplier: {2})").format(
                svc.item_name,
                svc.purchase_invoice,
                svc.supplier
            ),
            'is_wip_material': 0,  # Flag: This is a service cost
            'is_stock_item': 0,
            'expense_account': svc.expense_account,
            'source_reference': svc.purchase_invoice,
            'currency': svc.currency,
            'conversion_rate': flt(svc.conversion_rate),
            'transaction_amount': flt(svc.transaction_amount)
        }
        services.append(service)
        total_service_cost += base_amount
        purchase_invoices.add(svc.purchase_invoice)
    
    # ========================================
    # Return Combined Results
    # ========================================
    return {
        'materials': materials,
        'services': services,
        'total_material_cost': total_material_cost,
        'total_service_cost': total_service_cost,
        'purchase_invoices': list(purchase_invoices),
        'has_data': len(materials) > 0 or len(services) > 0,
        'company_currency': company_currency
    }
