# Copyright (c) 2025, abdulloh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class Kassa(Document):
    def validate(self):
        self.set_default_company()
        # kassa (visible) → cash_account (hidden) mirror — must run first
        # kassa_to (visible) → cash_account_to (hidden) mirror — same pattern
        self.sync_kassa_to_cash_account()
        # Currency derived from the GL account the cashier selected
        self.set_cash_account_currency()
        # MoP is a computed derivative of cash_account, not a driver
        self.derive_mop_from_account()
        self.set_party_currency()
        self.set_balance()
        self.validate_party()
        self.validate_transfer()
        self.validate_conversion()
        self.validate_amount()
        self.validate_currency()

    def on_submit(self):
        if self.transaction_type in ["Приход", "Расход"]:
            if self.party_type in ["Customer", "Supplier", "Employee", "Shareholder"]:
                self.create_payment_entry()
            elif self.party_type == "Дивиденд":
                self.create_dividend_journal_entry()
            elif self.party_type == "Расходы":
                self.create_expense_journal_entry()
        elif self.transaction_type == "Перемещения":
            self.create_transfer_payment_entry()
        elif self.transaction_type == "Конвертация":
            self.create_conversion_payment_entry()

    def on_cancel(self):
        self.cancel_linked_entries()

    # ─── ACCOUNT CREATION METHODS ────────────────────────────────────────────

    def create_payment_entry(self):
        payment_type = "Receive" if self.transaction_type == "Приход" else "Pay"
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")

        paid_from = self.get_paid_from_account(payment_type)
        paid_to = self.get_paid_to_account(payment_type)

        paid_from_currency = (
            frappe.get_cached_value("Account", paid_from, "account_currency")
            if paid_from else company_currency
        ) or company_currency
        paid_to_currency = (
            frappe.get_cached_value("Account", paid_to, "account_currency")
            if paid_to else company_currency
        ) or company_currency

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = payment_type
        pe.posting_date = self.date
        pe.company = self.company
        pe.mode_of_payment = self.mode_of_payment
        pe.party_type = self.party_type
        pe.party = self.party
        pe.paid_from = paid_from
        pe.paid_to = paid_to
        pe.paid_from_account_currency = paid_from_currency
        pe.paid_to_account_currency = paid_to_currency

        if paid_from_currency != company_currency:
            pe.source_exchange_rate = get_exchange_rate(paid_from_currency, company_currency, self.date) or 1
        else:
            pe.source_exchange_rate = 1

        if paid_to_currency != company_currency:
            pe.target_exchange_rate = get_exchange_rate(paid_to_currency, company_currency, self.date) or 1
        else:
            pe.target_exchange_rate = 1

        pe.paid_amount = flt(self.amount)
        pe.received_amount = flt(self.amount)
        pe.reference_no = self.name
        pe.reference_date = self.date
        pe.remarks = self.remarks or f"Payment for {self.name}"
        pe.flags.ignore_permissions = True
        pe.insert()
        pe.submit()
        frappe.msgprint(_("Payment Entry {0} создан").format(
            frappe.utils.get_link_to_form("Payment Entry", pe.name)
        ))

    def get_paid_from_account(self, payment_type):
        if payment_type == "Receive":
            if self.party_type == "Customer":
                return frappe.get_cached_value("Company", self.company, "default_receivable_account")
            elif self.party_type == "Supplier":
                return frappe.get_cached_value("Company", self.company, "default_payable_account")
            elif self.party_type in ["Employee", "Shareholder"]:
                return frappe.db.get_value("Account",
                    {"company": self.company, "account_type": "Payable", "is_group": 0}, "name")
        else:
            return self.cash_account

    def get_paid_to_account(self, payment_type):
        if payment_type == "Receive":
            return self.cash_account
        else:
            if self.party_type == "Customer":
                return frappe.get_cached_value("Company", self.company, "default_receivable_account")
            elif self.party_type == "Supplier":
                return frappe.get_cached_value("Company", self.company, "default_payable_account")
            elif self.party_type in ["Employee", "Shareholder"]:
                return frappe.db.get_value("Account",
                    {"company": self.company, "account_type": "Payable", "is_group": 0}, "name")

    def create_dividend_journal_entry(self):
        dividend_account = frappe.db.get_value("Account",
            {"company": self.company, "account_number": "3400", "is_group": 0}, "name")
        if not dividend_account:
            frappe.throw(_("Счет дивидендов (3400) не найден для компании {0}").format(self.company))

        cash_account_currency = frappe.get_cached_value("Account", self.cash_account, "account_currency")
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.name
        je.cheque_date = self.date
        je.user_remark = self.remarks or f"Dividend payment from {self.name}"

        is_multicurrency = cash_account_currency != "USD" and company_currency == "USD"
        if is_multicurrency:
            je.multi_currency = 1
            exchange_rate = get_exchange_rate("UZS", "USD", self.date) or 1
            je.append("accounts", {
                "account": self.cash_account,
                "credit_in_account_currency": flt(self.amount),
                "account_currency": cash_account_currency,
                "exchange_rate": exchange_rate,
                "credit": flt(self.amount) * exchange_rate
            })
            je.append("accounts", {
                "account": dividend_account,
                "debit_in_account_currency": flt(self.amount) * exchange_rate,
                "account_currency": company_currency,
                "exchange_rate": 1,
                "debit": flt(self.amount) * exchange_rate
            })
        else:
            je.append("accounts", {"account": self.cash_account,
                "credit_in_account_currency": flt(self.amount), "credit": flt(self.amount)})
            je.append("accounts", {"account": dividend_account,
                "debit_in_account_currency": flt(self.amount), "debit": flt(self.amount)})

        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        frappe.msgprint(_("Journal Entry {0} для дивидендов создан").format(
            frappe.utils.get_link_to_form("Journal Entry", je.name)
        ))

    def create_expense_journal_entry(self):
        if not self.expense_account:
            frappe.throw(_("Пожалуйста, выберите счет расходов"))

        cash_account_currency = frappe.get_cached_value("Account", self.cash_account, "account_currency")
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")
        expense_account_currency = frappe.get_cached_value(
            "Account", self.expense_account, "account_currency") or company_currency

        je = frappe.new_doc("Journal Entry")
        je.voucher_type = "Journal Entry"
        je.posting_date = self.date
        je.company = self.company
        je.cheque_no = self.name
        je.cheque_date = self.date
        je.user_remark = self.remarks or f"Expense payment from {self.name}"

        is_multicurrency = cash_account_currency != company_currency
        if is_multicurrency:
            je.multi_currency = 1
            exchange_rate = get_exchange_rate(cash_account_currency, company_currency, self.date) or 1
            je.append("accounts", {
                "account": self.cash_account,
                "credit_in_account_currency": flt(self.amount),
                "account_currency": cash_account_currency,
                "exchange_rate": exchange_rate,
                "credit": flt(self.amount) * exchange_rate
            })
            je.append("accounts", {
                "account": self.expense_account,
                "debit_in_account_currency": flt(self.amount) * exchange_rate,
                "account_currency": expense_account_currency,
                "exchange_rate": 1,
                "debit": flt(self.amount) * exchange_rate
            })
        else:
            je.append("accounts", {"account": self.cash_account,
                "credit_in_account_currency": flt(self.amount), "credit": flt(self.amount)})
            je.append("accounts", {"account": self.expense_account,
                "debit_in_account_currency": flt(self.amount), "debit": flt(self.amount)})

        je.flags.ignore_permissions = True
        je.insert()
        je.submit()
        frappe.msgprint(_("Journal Entry {0} для расходов создан").format(
            frappe.utils.get_link_to_form("Journal Entry", je.name)
        ))

    def create_transfer_payment_entry(self):
        """
        Same-company Internal Transfer: Cash ↔ Bank within one company.
        Payment Entry (Internal Transfer) requires both accounts in the same company.
        """
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Internal Transfer"
        pe.posting_date = self.date
        pe.company = self.company
        pe.mode_of_payment = self.mode_of_payment
        pe.paid_from = self.cash_account
        pe.paid_to = self.cash_account_to
        pe.paid_amount = flt(self.amount)
        pe.received_amount = flt(self.amount)
        pe.reference_no = self.name
        pe.reference_date = self.date
        pe.remarks = self.remarks or f"Transfer from {self.name}"
        pe.flags.ignore_permissions = True
        pe.insert()
        pe.submit()
        frappe.msgprint(_("Payment Entry {0} для перемещения создан").format(
            frappe.utils.get_link_to_form("Payment Entry", pe.name)
        ))

    def create_conversion_payment_entry(self):
        """
        Currency conversion between USD and UZS accounts.

        exchange_rate field label = "Курс (USD к UZS)" = e.g. 12500
        Meaning: 1 USD = 12500 UZS

        ERPNext source/target exchange_rate semantics:
            source_exchange_rate = how many company_currency units = 1 from_currency unit
            target_exchange_rate = how many company_currency units = 1 to_currency unit
        company_currency = USD

        Case A: UZS → USD (from_currency=UZS, to_currency=USD)
            source: 1 UZS = 1/12500 USD  → source_exchange_rate = 1/exchange_rate
            target: 1 USD = 1 USD         → target_exchange_rate = 1

        Case B: USD → UZS (from_currency=USD, to_currency=UZS)
            source: 1 USD = 1 USD         → source_exchange_rate = 1
            target: 1 UZS = 1/12500 USD  → target_exchange_rate = 1/exchange_rate
        """
        from_currency = frappe.get_cached_value("Account", self.cash_account, "account_currency")
        to_currency = frappe.get_cached_value("Account", self.cash_account_to, "account_currency")
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")

        exchange_rate = flt(self.exchange_rate)
        if exchange_rate <= 0:
            frappe.throw(_("Курс обмена должен быть больше нуля"))

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Internal Transfer"
        pe.posting_date = self.date
        pe.company = self.company
        pe.mode_of_payment = self.mode_of_payment
        pe.paid_from = self.cash_account
        pe.paid_to = self.cash_account_to
        pe.paid_amount = flt(self.debit_amount)
        pe.received_amount = flt(self.credit_amount)

        # source_exchange_rate: 1 unit of from_currency = ? company_currency
        if from_currency == company_currency:
            pe.source_exchange_rate = 1
        else:
            # from_currency is UZS, company is USD → 1 UZS = 1/12500 USD
            pe.source_exchange_rate = flt(1 / exchange_rate, 9)

        # target_exchange_rate: 1 unit of to_currency = ? company_currency
        if to_currency == company_currency:
            pe.target_exchange_rate = 1
        else:
            # to_currency is UZS, company is USD → 1 UZS = 1/12500 USD
            pe.target_exchange_rate = flt(1 / exchange_rate, 9)

        pe.reference_no = self.name
        pe.reference_date = self.date
        pe.remarks = self.remarks or f"Conversion from {self.name}"
        pe.flags.ignore_permissions = True
        pe.insert()
        pe.submit()
        frappe.msgprint(_("Payment Entry {0} для конвертации создан").format(
            frappe.utils.get_link_to_form("Payment Entry", pe.name)
        ))

    def cancel_linked_entries(self):
        for pe_name in frappe.get_all("Payment Entry",
                filters={"reference_no": self.name, "docstatus": 1}, pluck="name"):
            pe = frappe.get_doc("Payment Entry", pe_name)
            pe.flags.ignore_permissions = True
            pe.cancel()
            frappe.msgprint(_("Payment Entry {0} отменен").format(pe_name))

        for je_name in frappe.get_all("Journal Entry",
                filters={"cheque_no": self.name, "docstatus": 1}, pluck="name"):
            je_doc = frappe.get_doc("Journal Entry", je_name)
            je_doc.flags.ignore_permissions = True
            je_doc.cancel()
            frappe.msgprint(_("Journal Entry {0} отменен").format(je_name))

    # ─── VALIDATION & SETTER METHODS ─────────────────────────────────────────

    def set_default_company(self):
        """
        Resolve company from Global Defaults at validate time.
        Server-side guard against client-side race conditions.
        """
        if not self.company:
            default_company = frappe.db.get_single_value("Global Defaults", "default_company")
            if default_company:
                self.company = default_company
            else:
                frappe.throw(_("Пожалуйста, установите компанию по умолчанию в настройках"))

    def sync_kassa_to_cash_account(self):
        """
        kassa (visible Link → Account) is the cashier's primary source selector.
        cash_account (hidden Link → Account) is what all accounting methods use.

        kassa_to (visible) → cash_account_to (hidden): same pattern for destination.

        This guarantees accounting logic always operates on validated account references,
        while the UI presents a user-friendly account picker via kassa / kassa_to.
        """
        if self.kassa:
            self.cash_account = self.kassa

        if self.transaction_type in ["Перемещения", "Конвертация"]:
            if self.kassa_to:
                self.cash_account_to = self.kassa_to
            else:
                self.cash_account_to = None

    def set_cash_account_currency(self):
        """Derive cash_account_currency directly from the selected cash_account's GL record."""
        if self.cash_account:
            self.cash_account_currency = frappe.get_cached_value(
                "Account", self.cash_account, "account_currency")

    def derive_mop_from_account(self):
        """
        ACCOUNT-FIRST: Mode of Payment is automatically derived from the selected
        cash_account via a reverse lookup on Mode of Payment Account records.
        The cashier selects an Account (kassa); MoP is computed, not chosen.

        Only source MoP is derived here. Destination account (kassa_to / cash_account_to)
        drives no MoP field — it is used directly in accounting entries.
        """
        if self.cash_account and self.company:
            mop = get_mop_for_account(self.cash_account, self.company)
            if mop:
                self.mode_of_payment = mop
            else:
                frappe.throw(
                    _("Для счета «{0}» не найден способ оплаты. "
                      "Проверьте настройки Mode of Payment для компании «{1}».").format(
                        self.cash_account, self.company)
                )

    def set_party_currency(self):
        if self.party and self.party_type in ["Customer", "Supplier"] and self.company:
            self.party_currency = get_party_currency(self.party_type, self.party, self.company)

    def set_balance(self):
        if self.cash_account:
            self.balance = get_account_balance(self.cash_account, self.company)
        if self.cash_account_to:
            self.balance_to = get_account_balance(
                self.cash_account_to,
                frappe.get_cached_value("Account", self.cash_account_to, "company")
            )

    def validate_party(self):
        if self.transaction_type in ["Приход", "Расход"]:
            if not self.party_type:
                frappe.throw(_("Пожалуйста, выберите тип контрагента"))
            if self.party_type == "Расходы":
                if not self.expense_account:
                    frappe.throw(_("Пожалуйста, выберите счет расходов"))
                self.party = None
            elif self.party_type == "Дивиденд":
                self.party = None
                self.expense_account = None
            else:
                if not self.party:
                    frappe.throw(_("Пожалуйста, выберите контрагента"))
                self.expense_account = None

    def validate_transfer(self):
        """
        Перемещения rules (same company only for now):
        - Source and destination must be different accounts.
        - Source and destination must belong to the same company.
        - Allowed direction: Cash ↔ Bank (not Cash ↔ Cash, not Bank ↔ Bank).
          Rationale: Moving between two cash drawers or two bank accounts
          has no operational meaning in this business model.
        """
        if self.transaction_type != "Перемещения":
            return

        if not self.cash_account_to:
            frappe.throw(_("Пожалуйста, выберите счет кассы (куда)"))

        if self.cash_account == self.cash_account_to:
            frappe.throw(_("Счет источника и назначения должны отличаться"))

        # Same-company constraint (cross-company deferred to Phase 2)
        company_from = frappe.get_cached_value("Account", self.cash_account, "company")
        company_to = frappe.get_cached_value("Account", self.cash_account_to, "company")
        if company_from != company_to:
            frappe.throw(
                _("Перемещение между компаниями временно не поддерживается. "
                  "Выберите счет в рамках одной компании.")
            )

        # Cash ↔ Bank directional constraint
        type_from = frappe.get_cached_value("Account", self.cash_account, "account_type")
        type_to = frappe.get_cached_value("Account", self.cash_account_to, "account_type")
        allowed = (
            (type_from == "Cash" and type_to == "Bank") or
            (type_from == "Bank" and type_to == "Cash")
        )
        if not allowed:
            frappe.throw(
                _("Перемещение разрешено только между счетами типа Cash и Bank. "
                  "Источник: {0}, Назначение: {1}").format(type_from, type_to)
            )

    def validate_conversion(self):
        """
        Конвертация rules:
        - Source and destination must have different currencies (USD ↔ UZS).
        - exchange_rate, debit_amount, credit_amount must be positive.
        - Both accounts must be Cash or Bank type (enforced by get_kassa_accounts filter).
        """
        if self.transaction_type != "Конвертация":
            return

        if not self.cash_account_to:
            frappe.throw(_("Пожалуйста, выберите счет кассы (куда)"))

        if not self.exchange_rate or flt(self.exchange_rate) <= 0:
            frappe.throw(_("Пожалуйста, укажите курс обмена"))

        if flt(self.debit_amount) <= 0:
            frappe.throw(_("Пожалуйста, укажите сумму расхода"))

        if flt(self.credit_amount) <= 0:
            frappe.throw(_("Пожалуйста, укажите сумму прихода"))

        from_currency = frappe.get_cached_value("Account", self.cash_account, "account_currency")
        to_currency = frappe.get_cached_value("Account", self.cash_account_to, "account_currency")

        if from_currency == to_currency:
            frappe.throw(
                _("Для конвертации счета должны иметь разные валюты. "
                  "Оба счета имеют валюту: {0}").format(from_currency)
            )

        # Guard: only USD ↔ UZS conversions are supported
        allowed_pairs = [("USD", "UZS"), ("UZS", "USD")]
        if (from_currency, to_currency) not in allowed_pairs:
            frappe.throw(
                _("Конвертация поддерживается только между USD и UZS. "
                  "Выбрано: {0} → {1}").format(from_currency, to_currency)
            )

    def validate_amount(self):
        if self.transaction_type == "Конвертация":
            return
        if flt(self.amount) <= 0:
            frappe.throw(_("Сумма должна быть больше нуля"))
        if self.transaction_type == "Расход" and flt(self.amount) > flt(self.balance):
            frappe.msgprint(
                _("Внимание: Сумма расхода ({0}) превышает остаток кассы ({1})").format(
                    frappe.format_value(self.amount, {"fieldtype": "Currency"}),
                    frappe.format_value(self.balance, {"fieldtype": "Currency"})
                ),
                indicator="orange", alert=True
            )

    def validate_currency(self):
        if self.transaction_type not in ["Приход", "Расход"]:
            return
        if self.party_type not in ["Customer", "Supplier"]:
            return
        if not self.cash_account_currency or not self.party_currency:
            return
        if self.cash_account_currency != self.party_currency:
            frappe.throw(
                _("Валюта кассы ({0}) не совпадает с валютой контрагента ({1}). "
                  "Выберите соответствующий счет кассы.").format(
                    self.cash_account_currency, self.party_currency)
            )


# ─── WHITELISTED API HELPERS ─────────────────────────────────────────────────

@frappe.whitelist()
def get_mop_for_account(account, company):
    """
    ACCOUNT-FIRST reverse lookup.
    Given a GL Account and Company, returns the Mode of Payment whose
    Mode of Payment Account mapping claims this account as its default.
    """
    if not account or not company:
        return None
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"default_account": account, "company": company},
        "parent"
    )


@frappe.whitelist()
def get_cash_account(mode_of_payment, company):
    """Legacy: MoP → Account lookup. Retained for backward compatibility."""
    if not mode_of_payment or not company:
        return None
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account"
    )


@frappe.whitelist()
def get_cash_account_with_currency(mode_of_payment, company):
    """Legacy: MoP → Account + Currency. Retained for backward compatibility."""
    if not mode_of_payment or not company:
        return {"account": None, "currency": None}
    account = frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account"
    )
    if account:
        currency = frappe.get_cached_value("Account", account, "account_currency")
        return {"account": account, "currency": currency}
    return {"account": None, "currency": None}


@frappe.whitelist()
def get_party_currency(party_type, party, company):
    if not party_type or not party or not company:
        return None
    currency = None
    if party_type in ["Customer", "Supplier"]:
        account = frappe.db.get_value(
            "Party Account",
            {"parenttype": party_type, "parent": party, "company": company},
            "account"
        )
        if account:
            currency = frappe.get_cached_value("Account", account, "account_currency")
        if not currency:
            currency = frappe.get_cached_value(party_type, party, "default_currency")
        if not currency:
            currency = frappe.get_cached_value("Company", company, "default_currency")
    else:
        currency = frappe.get_cached_value("Company", company, "default_currency")
    return currency


@frappe.whitelist()
def get_account_balance(account, company):
    if not account:
        return 0
    balance = frappe.db.sql("""
        SELECT SUM(debit_in_account_currency) - SUM(credit_in_account_currency) AS balance
        FROM `tabGL Entry`
        WHERE account = %s AND company = %s AND is_cancelled = 0
    """, (account, company), as_dict=True)
    return flt(balance[0].balance) if balance and balance[0].balance else 0


@frappe.whitelist()
def get_kassa_accounts(doctype, txt, searchfield, start, page_len, filters):
    """
    SERVER-SIDE SECURITY BOUNDARY for source kassa field.
    Returns only Cash/Bank ledgers for the given company.
    Prevents cashiers from selecting non-cash GL Accounts.
    """
    company = filters.get("company") if filters else None
    if not company:
        return []
    return frappe.db.sql(
        """
        SELECT name, account_name, account_currency
        FROM   `tabAccount`
        WHERE  company      = %(company)s
          AND  account_type IN ('Cash', 'Bank')
          AND  is_group     = 0
          AND  (name LIKE %(txt)s OR account_name LIKE %(txt)s)
        ORDER  BY account_type, name
        LIMIT  %(start)s, %(page_len)s
        """,
        {"company": company, "txt": f"%{txt}%", "start": start, "page_len": page_len},
    )


@frappe.whitelist()
def get_kassa_accounts_to(doctype, txt, searchfield, start, page_len, filters):
    """
    kassa_to field query: Cash/Bank accounts across ALL companies.

    For Перемещения (same company): results are further validated in
    validate_transfer() which throws if company_from != company_to.

    For Конвертация: same company required for Payment Entry (Internal Transfer).
    Both constraints are enforced server-side at submit time, not at search time,
    so the cashier can see all available accounts and pick the correct one.

    Shows company name in results so cashier can distinguish accounts visually.
    """
    company_filter = filters.get("company") if filters else None
    params = {"txt": f"%{txt}%", "start": start, "page_len": page_len}

    if company_filter:
        params["company"] = company_filter
        company_clause = "AND company = %(company)s"
    else:
        company_clause = ""

    return frappe.db.sql(
        f"""
        SELECT name, account_name, account_currency, company
        FROM   `tabAccount`
        WHERE  account_type IN ('Cash', 'Bank')
          AND  is_group     = 0
          {company_clause}
          AND  (name LIKE %(txt)s OR account_name LIKE %(txt)s)
        ORDER  BY company, account_type, name
        LIMIT  %(start)s, %(page_len)s
        """,
        params,
    )


@frappe.whitelist()
def get_expense_accounts(doctype, txt, searchfield, start, page_len, filters):
    company = (filters.get("company") if filters else None) or frappe.defaults.get_user_default("company")
    if not company:
        return []
    return frappe.db.sql("""
        SELECT name, account_name
        FROM `tabAccount`
        WHERE company = %(company)s AND root_type = 'Expense' AND is_group = 0
        AND (name LIKE %(txt)s OR account_name LIKE %(txt)s)
        ORDER BY name
        LIMIT %(start)s, %(page_len)s
    """, {"company": company, "txt": f"%{txt}%", "start": start, "page_len": page_len})


@frappe.whitelist()
def get_exchange_rate(from_currency, to_currency, date=None):
    if not date:
        date = frappe.utils.today()
    exchange_rate = frappe.db.get_value(
        "Currency Exchange",
        {"from_currency": from_currency, "to_currency": to_currency, "date": ("<=", date)},
        "exchange_rate", order_by="date desc"
    )
    if exchange_rate:
        return flt(exchange_rate)
    reverse_rate = frappe.db.get_value(
        "Currency Exchange",
        {"from_currency": to_currency, "to_currency": from_currency, "date": ("<=", date)},
        "exchange_rate", order_by="date desc"
    )
    if reverse_rate and flt(reverse_rate) > 0:
        return flt(1 / flt(reverse_rate), 4)
    return 0
