# Copyright (c) 2025, abdulloh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class Kassa(Document):
    def validate(self):
        self.set_default_company()
        self.set_cash_account()
        self.set_cash_account_currency()
        self.set_party_currency()
        self.set_balance()
        self.validate_party()
        self.validate_transfer()
        self.validate_conversion()
        self.validate_amount()
        self.validate_currency()

    def on_submit(self):
        if self.transaction_type in ["Приход", "Расход"]:
            if self.party_type in ["Customer", "Supplier", "Employee"]:
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

    # ─── ACCOUNT CREATION METHODS (unchanged) ────────────────────────────────

    def create_payment_entry(self):
        payment_type = "Receive" if self.transaction_type == "Приход" else "Pay"
        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = payment_type
        pe.posting_date = self.date
        pe.company = self.company
        pe.mode_of_payment = self.mode_of_payment
        pe.party_type = self.party_type
        pe.party = self.party
        pe.paid_from = self.get_paid_from_account(payment_type)
        pe.paid_to = self.get_paid_to_account(payment_type)
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
            elif self.party_type == "Employee":
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
            elif self.party_type == "Employee":
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
        from_currency = frappe.get_cached_value("Account", self.cash_account, "account_currency")
        to_currency = frappe.get_cached_value("Account", self.cash_account_to, "account_currency")
        company_currency = frappe.get_cached_value("Company", self.company, "default_currency")

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Internal Transfer"
        pe.posting_date = self.date
        pe.company = self.company
        pe.mode_of_payment = self.mode_of_payment
        pe.paid_from = self.cash_account
        pe.paid_to = self.cash_account_to
        pe.paid_amount = flt(self.debit_amount)
        pe.received_amount = flt(self.credit_amount)

        if from_currency != company_currency:
            pe.source_exchange_rate = flt(1 / flt(self.exchange_rate), 9) if flt(self.exchange_rate) > 0 else 1
        else:
            pe.source_exchange_rate = 1

        if to_currency != company_currency:
            pe.target_exchange_rate = flt(1 / flt(self.exchange_rate), 9) if flt(self.exchange_rate) > 0 else 1
        else:
            pe.target_exchange_rate = 1

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

    # ─── VALIDATION SETTERS ──────────────────────────────────────────────────

    def set_default_company(self):
        """
        FIX: For Перемещения, resolve company from Global Defaults at validate time.
        This is the server-side guard against the client-side race condition where
        company may not yet be set when set_cash_account fires during JS execution.
        """
        if self.transaction_type == "Перемещения" and not self.company:
            default_company = frappe.db.get_single_value("Global Defaults", "default_company")
            if default_company:
                self.company = default_company
            else:
                frappe.throw(_("Пожалуйста, установите компанию по умолчанию в настройках"))

    def set_cash_account(self):
        """
        FIX: Guard against null company before querying Mode of Payment Account.
        Previously this would silently return None if company was not yet resolved,
        leaving cash_account empty and causing a confusing submit-time error.
        """
        if not self.company:
            # company not resolved yet — set_default_company must run first in validate()
            return

        if self.mode_of_payment and self.company:
            cash_account = get_cash_account(self.mode_of_payment, self.company)
            if cash_account:
                self.cash_account = cash_account

        if self.mode_of_payment_to and self.company:
            cash_account_to = get_cash_account(self.mode_of_payment_to, self.company)
            if cash_account_to:
                self.cash_account_to = cash_account_to

    def set_cash_account_currency(self):
        if self.cash_account:
            self.cash_account_currency = frappe.get_cached_value(
                "Account", self.cash_account, "account_currency")

    def set_party_currency(self):
        if self.party and self.party_type in ["Customer", "Supplier"] and self.company:
            self.party_currency = get_party_currency(self.party_type, self.party, self.company)

    def set_balance(self):
        if self.cash_account:
            self.balance = get_account_balance(self.cash_account, self.company)
        if self.cash_account_to:
            self.balance_to = get_account_balance(self.cash_account_to, self.company)

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
        if self.transaction_type == "Перемещения":
            if not self.mode_of_payment_to:
                frappe.throw(_("Пожалуйста, выберите способ оплаты (куда)"))
            if self.mode_of_payment == self.mode_of_payment_to:
                frappe.throw(_("Способ оплаты источника и назначения должны отличаться"))
            allowed_combinations = [("Cash UZS", "Bank (No ref)"), ("Bank (No ref)", "Cash UZS")]
            if (self.mode_of_payment, self.mode_of_payment_to) not in allowed_combinations:
                frappe.throw(_("Для перемещения разрешены только комбинации: Cash UZS <-> Bank (No ref)"))

    def validate_conversion(self):
        if self.transaction_type == "Конвертация":
            if not self.mode_of_payment_to:
                frappe.throw(_("Пожалуйста, выберите способ оплаты (куда)"))
            if not self.exchange_rate or flt(self.exchange_rate) <= 0:
                frappe.throw(_("Пожалуйста, укажите курс обмена"))
            if flt(self.debit_amount) <= 0:
                frappe.throw(_("Пожалуйста, укажите сумму расхода"))
            if flt(self.credit_amount) <= 0:
                frappe.throw(_("Пожалуйста, укажите сумму прихода"))
            allowed_combinations = [
                ("Cash UZS", "Cash USD"), ("Bank (No ref)", "Cash USD"),
                ("Cash USD", "Cash UZS"), ("Cash USD", "Bank (No ref)")
            ]
            if (self.mode_of_payment, self.mode_of_payment_to) not in allowed_combinations:
                frappe.throw(_("Для конвертации разрешены только комбинации: Cash UZS/Bank (No ref) <-> Cash USD"))

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
                  "Выберите соответствующий способ оплаты.").format(
                    self.cash_account_currency, self.party_currency)
            )


# ─── WHITELISTED API HELPERS ─────────────────────────────────────────────────

@frappe.whitelist()
def get_cash_account(mode_of_payment, company):
    if not mode_of_payment or not company:
        return None
    return frappe.db.get_value(
        "Mode of Payment Account",
        {"parent": mode_of_payment, "company": company},
        "default_account"
    )


@frappe.whitelist()
def get_cash_account_with_currency(mode_of_payment, company):
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
    SERVER-SIDE SECURITY BOUNDARY.
    Filters are extracted here on the server — not trusted from the client payload.
    Even if a malicious actor modifies the JS filter object, this function
    enforces company scoping at the SQL level with no bypass path.

    WHY account_type IN ('Cash', 'Bank') and NOT root_type IN ('Asset', 'Liability'):
    root_type = 'Asset' captures every asset leaf: Buildings, Accumulated Depreciation,
    Fixed Assets, etc. — all of which are irrelevant to a cash register.
    account_type is the precise ERPNext classification that identifies actual
    cash drawers and bank ledgers. This is the correct discriminator.
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