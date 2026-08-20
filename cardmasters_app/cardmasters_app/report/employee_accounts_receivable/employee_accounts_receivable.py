# Copyright (c) 2026, Your Company and Contributors
# License: GNU General Public License v3. See license.txt

from collections import OrderedDict

import frappe
from frappe import _, qb, query_builder, scrub
from frappe.query_builder import Criterion
from frappe.query_builder.functions import Date, Substring, Sum
from frappe.utils import cint, cstr, flt, getdate, nowdate

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children
from erpnext.accounts.utils import (
	build_qb_match_conditions,
	get_advance_payment_doctypes,
	get_currency_precision,
)

# This report calculates aging summaries for Employee Ledger Entries / Advances

def execute(filters=None):
	args = {
		"account_type": "Receivable",
		"naming_by": ["Global Defaults", "default_company"],  # Safe fallback to prevent setup errors
	}
	return ReceivablePayableReport(filters).run(args)


class ReceivablePayableReport:
	def __init__(self, filters=None):
		self.filters = frappe._dict(filters or {})
		self.qb_selection_filter = []
		self.ple = qb.DocType("Payment Ledger Entry")
		self.account = qb.DocType("Account")
		self.filters.report_date = getdate(self.filters.report_date or nowdate())
		self.age_as_on = (
			getdate(nowdate())
			if "calculate_ageing_with" not in self.filters
			or self.filters.calculate_ageing_with == "Today Date"
			else self.filters.report_date
		)

		if not self.filters.range:
			self.filters.range = "30, 60, 90, 120"
		self.ranges = [num.strip() for num in self.filters.range.split(",") if num.strip().isdigit()]
		self.range_numbers = [num for num in range(1, len(self.ranges) + 2)]
		self.ple_fetch_method = (
			frappe.db.get_single_value("Accounts Settings", "receivable_payable_fetch_method")
			or "Buffered Cursor"
		)
		self.advance_payment_doctypes = get_advance_payment_doctypes()
		self.err_journals = []

	def run(self, args):
		self.filters.update(args)
		self.set_defaults()
		self.party_naming_by = "Naming Series"
		self.get_columns()
		self.get_data()
		self.get_chart_data()
		return self.columns, self.data, None, self.chart, None, self.skip_total_row

	def set_defaults(self):
		if not self.filters.get("company"):
			self.filters.company = frappe.db.get_single_value("Global Defaults", "default_company")
		self.company_currency = frappe.get_cached_value(
			"Company", self.filters.get("company"), "default_currency"
		)
		self.currency_precision = get_currency_precision() or 2
		self.dr_or_cr = "debit"
		self.account_type = self.filters.account_type
		
		# FIXED: Hardcoded to target Employee documents exclusively
		self.party_type = ["Employee"]
		self.party_details = {}
		self.invoices = set()
		self.skip_total_row = 0
		self.advance_payment_doctypes = get_advance_payment_doctypes()

		if self.filters.get("group_by_party"):
			self.previous_party = ""
			self.total_row_map = {}
			self.skip_total_row = 1

		if self.filters.get("in_party_currency"):
			if self.filters.get("party") and len(self.filters.get("party")) == 1:
				self.skip_total_row = 0
			else:
				self.skip_total_row = 1

	def get_data(self):
		# Stripped out Sales Person and Return Voucher filters to prevent schema query exceptions
		self.get_invoice_details()
		self.get_future_payments()
		self.get_exchange_rate_revaluations()

		self.prepare_ple_query()
		self.data = []
		self.voucher_balance = OrderedDict()

		if self.ple_fetch_method == "Buffered Cursor":
			self.fetch_ple_in_buffered_cursor()
		elif self.ple_fetch_method == "UnBuffered Cursor":
			self.fetch_ple_in_unbuffered_cursor()

		self.build_data()

	def fetch_ple_in_buffered_cursor(self):
		self.ple_entries = self.ple_query.run(as_dict=True)
		for ple in self.ple_entries:
			self.init_voucher_balance(ple)
		for ple in self.ple_entries:
			self.update_voucher_balance(ple)
		delattr(self, "ple_entries")

	def fetch_ple_in_unbuffered_cursor(self):
		self.ple_entries = []
		with frappe.db.unbuffered_cursor():
			for ple in self.ple_query.run(as_dict=True, as_iterator=True):
				self.init_voucher_balance(ple)
				self.ple_entries.append(ple)

		for ple in self.ple_entries:
			self.update_voucher_balance(ple)
		delattr(self, "ple_entries")

	def build_voucher_dict(self, ple):
		return frappe._dict(
			voucher_type=ple.voucher_type,
			voucher_no=ple.voucher_no,
			party=ple.party,
			party_account=ple.account,
			posting_date=ple.posting_date,
			account_currency=ple.account_currency,
			remarks=ple.remarks,
			invoiced=0.0,
			paid=0.0,
			credit_note=0.0,
			outstanding=0.0,
			invoiced_in_account_currency=0.0,
			paid_in_account_currency=0.0,
			credit_note_in_account_currency=0.0,
			outstanding_in_account_currency=0.0,
		)

	def init_voucher_balance(self, ple):
		if self.filters.get("ignore_accounts"):
			key = (ple.voucher_type, ple.voucher_no, ple.party)
		else:
			key = (ple.account, ple.voucher_type, ple.voucher_no, ple.party)

		if key not in self.voucher_balance:
			self.voucher_balance[key] = self.build_voucher_dict(ple)

		if (ple.voucher_type == ple.against_voucher_type and ple.voucher_no == ple.against_voucher_no) or (
			ple.voucher_type in ("Payment Entry", "Journal Entry")
			and ple.against_voucher_type in self.advance_payment_doctypes
		):
			self.voucher_balance[key].cost_center = ple.cost_center
			self.voucher_balance[key].project = ple.project

		if self.filters.get("group_by_party"):
			self.init_subtotal_row(ple.party)

		if self.filters.get("group_by_party") and not self.filters.get("in_party_currency"):
			self.init_subtotal_row("Total")

	def init_subtotal_row(self, party):
		if not self.total_row_map.get(party):
			self.total_row_map.setdefault(party, {"party": party, "bold": 1})
			for field in self.get_currency_fields():
				self.total_row_map[party][field] = 0.0

	def get_currency_fields(self):
		return [
			"invoiced", "paid", "credit_note", "outstanding",
			"range1", "range2", "range3", "range4", "range5",
			"future_amount", "remaining_balance",
		]

	def get_voucher_balance(self, ple):
		if self.filters.get("ignore_accounts"):
			key = (ple.against_voucher_type, ple.against_voucher_no, ple.party)
		else:
			key = (ple.account, ple.against_voucher_type, ple.against_voucher_no, ple.party)

		row = self.voucher_balance.get(key)

		if not row:
			if self.filters.get("ignore_accounts"):
				row = self.voucher_balance.get((ple.voucher_type, ple.voucher_no, ple.party))
			else:
				row = self.voucher_balance.get((ple.account, ple.voucher_type, ple.voucher_no, ple.party))

		if row:
			row.party_type = ple.party_type
		return row

	def update_voucher_balance(self, ple):
		row = self.get_voucher_balance(ple)
		if not row:
			return

		if self.filters.get("in_party_currency") or self.filters.get("party_account"):
			amount = ple.amount_in_account_currency
		else:
			amount = ple.amount
		amount_in_account_currency = ple.amount_in_account_currency

		if ple.amount > 0:
			if (ple.voucher_type in ["Journal Entry", "Payment Entry"] and ple.voucher_no != ple.against_voucher_no):
				row.paid -= amount
				row.paid_in_account_currency -= amount_in_account_currency
			else:
				row.invoiced += amount
				row.invoiced_in_account_currency += amount_in_account_currency
		else:
			if ple.voucher_type in ("Sales Invoice", "Purchase Invoice"):
				if row.voucher_no == ple.voucher_no == ple.against_voucher_no:
					row.paid -= amount
					row.paid_in_account_currency -= amount_in_account_currency
				else:
					row.credit_note -= amount
					row.credit_note_in_account_currency -= amount_in_account_currency
			else:
				row.paid -= amount
				row.paid_in_account_currency -= amount_in_account_currency

	def update_sub_total_row(self, row, party):
		total_row = self.total_row_map.get(party)
		if total_row:
			for field in self.get_currency_fields():
				total_row[field] += row.get(field, 0.0)
			total_row["currency"] = row.get("currency", "")

	def append_subtotal_row(self, party):
		sub_total_row = self.total_row_map.get(party)
		if sub_total_row:
			self.data.append(sub_total_row)
			self.data.append({})
			self.update_sub_total_row(sub_total_row, "Total")

	def build_data(self):
		for _key, row in self.voucher_balance.items():
			row.outstanding = flt(row.invoiced - row.paid - row.credit_note, self.currency_precision)
			row.outstanding_in_account_currency = flt(
				row.invoiced_in_account_currency - row.paid_in_account_currency - row.credit_note_in_account_currency,
				self.currency_precision,
			)
			row.invoice_grand_total = row.invoiced

			must_consider = False
			if (abs(row.outstanding) >= 1.0 / 10**self.currency_precision) or (
				abs(row.outstanding_in_account_currency) >= 1.0 / 10**self.currency_precision
			):
				must_consider = True

			if must_consider:
				self.append_row(row)

		if self.filters.get("group_by_party"):
			self.append_subtotal_row(self.previous_party)
			if self.data:
				self.data.append(self.total_row_map.get("Total", {}))

	def append_row(self, row):
		self.allocate_future_payments(row)
		self.set_invoice_details(row)
		self.set_party_details(row)
		self.set_ageing(row)

		if self.filters.get("group_by_party"):
			self.update_sub_total_row(row, row.party)
			if self.previous_party and (self.previous_party != row.party):
				self.append_subtotal_row(self.previous_party)
			self.previous_party = row.party

		self.data.append(row)

	def set_invoice_details(self, row):
		invoice_details = self.invoice_details.get(row.voucher_no, {})
		if row.due_date:
			invoice_details.pop("due_date", None)
		row.update(invoice_details)

	def get_invoice_details(self):
		self.invoice_details = frappe._dict()
		
		# Track dynamic journals booked via general accounting entries
		journal_entries = frappe.get_list(
			"Journal Entry",
			filters={
				"posting_date": ("<=", self.filters.report_date),
				"company": self.filters.company,
				"docstatus": 1,
			},
			fields=["name", "due_date", "bill_no", "bill_date"],
		)
		for je in journal_entries:
			if je.bill_no:
				self.invoice_details.setdefault(je.name, je)

	def set_party_details(self, row):
		if not row.party:
			return
		party_details = self.get_party_details(row.party) or {}
		row.update(party_details)
		row.currency = row.account_currency if (self.filters.get("in_party_currency") or self.filters.get("party_account")) else self.company_currency

	def get_future_payments(self):
		if self.filters.show_future_payments:
			self.future_payments = frappe._dict()
			future_payments = list(self.get_future_payments_from_payment_entry())
			future_payments += list(self.get_future_payments_from_journal_entry())
			if future_payments:
				for d in future_payments:
					if d.future_amount and d.invoice_no:
						self.future_payments.setdefault((d.invoice_no, d.party), []).append(d)

	def get_future_payments_from_payment_entry(self):
		pe = frappe.qb.DocType("Payment Entry")
		pe_ref = frappe.qb.DocType("Payment Entry Reference")
		ifelse = query_builder.CustomFunction("IF", ["condition", "then", "else"])

		return (
			frappe.qb.from_(pe)
			.inner_join(pe_ref).on(pe_ref.parent == pe.name)
			.select(
				(pe_ref.reference_name).as_("invoice_no"),
				pe.party,
				pe.party_type,
				(pe.posting_date).as_("future_date"),
				(pe_ref.allocated_amount).as_("future_amount"),
				(pe.reference_no).as_("future_ref"),
				ifelse(
					pe.payment_type == "Receive",
					pe.source_exchange_rate * pe_ref.allocated_amount,
					pe.target_exchange_rate * pe_ref.allocated_amount,
				).as_("future_amount_in_base_currency"),
			)
			.where(
				(pe.docstatus < 2)
				& (pe.posting_date > self.filters.report_date)
				& (pe.party_type.isin(self.party_type))
			)
		).run(as_dict=True)

	def get_future_payments_from_journal_entry(self):
		je = frappe.qb.DocType("Journal Entry")
		jea = frappe.qb.DocType("Journal Entry Account")
		query = (
			frappe.qb.from_(je)
			.inner_join(jea).on(jea.parent == je.name)
			.select(
				jea.reference_name.as_("invoice_no"),
				jea.party,
				jea.party_type,
				je.posting_date.as_("future_date"),
				je.cheque_no.as_("future_ref"),
			)
			.where(
				(je.docstatus < 2)
				& (je.posting_date > self.filters.report_date)
				& (jea.party_type.isin(self.party_type))
				& (jea.reference_name.isnotnull())
				& (jea.reference_name != "")
			)
		)

		if self.filters.get("party"):
			query = query.select(Sum(jea.credit_in_account_currency - jea.debit_in_account_currency).as_("future_amount"))
			query = query.select(Sum(jea.credit - jea.debit).as_("future_amount_in_base_currency"))
		else:
			query = query.select(Sum(jea.credit).as_("future_amount_in_base_currency"))
			query = query.select(Sum(jea.credit_in_account_currency).as_("future_amount"))

		query = query.having(qb.Field("future_amount") > 0)
		return query.run(as_dict=True)

	def allocate_future_payments(self, row):
		if not self.filters.show_future_payments:
			return

		row.remaining_balance = row.outstanding
		row.future_amount = 0.0
		for future in self.future_payments.get((row.voucher_no, row.party), []):
			future_amount_field = "future_amount" if self.filters.in_party_currency else "future_amount_in_base_currency"

			if row.remaining_balance != 0 and future.get(future_amount_field):
				if future.get(future_amount_field) > row.outstanding:
					row.future_amount = row.outstanding
					future[future_amount_field] = future.get(future_amount_field) - row.outstanding
					row.remaining_balance = 0
				else:
					row.future_amount += future.get(future_amount_field)
					future[future_amount_field] = 0
					row.remaining_balance = row.outstanding - row.future_amount

				row.setdefault("future_ref", []).append(cstr(future.future_ref) + "/" + cstr(future.future_date))

		if row.future_ref:
			row.future_ref = ", ".join(row.future_ref)

	def set_ageing(self, row):
		entry_date = row.posting_date
		self.get_ageing_data(entry_date, row)
		if getdate(entry_date) > getdate(self.age_as_on):
			[setattr(row, f"range{i}", 0.0) for i in self.range_numbers]
		row.total_due = sum(row[f"range{i}"] for i in self.range_numbers)

	def get_ageing_data(self, entry_date, row):
		[setattr(row, f"range{i}", 0.0) for i in self.range_numbers]
		if not (self.age_as_on and entry_date):
			return

		row.age = (getdate(self.age_as_on) - getdate(entry_date)).days or 0
		index = next((i for i, days in enumerate(self.ranges) if cint(row.age) <= cint(days)), len(self.ranges))
		row["range" + str(index + 1)] = row.outstanding

	def prepare_ple_query(self):
		self.prepare_conditions()

		if self.filters.show_future_payments:
			self.qb_selection_filter.append(
				self.ple.posting_date.lte(self.filters.report_date)
				| ((self.ple.voucher_no == self.ple.against_voucher_no) & (Date(self.ple.creation).lte(self.filters.report_date)))
			)
		else:
			self.qb_selection_filter.append(self.ple.posting_date.lte(self.filters.report_date))

		query = (
			qb.from_(self.ple)
			.inner_join(self.account)
			.on(self.account.name == self.ple.account)
			.select(
				self.ple.name, self.ple.account, self.ple.voucher_type, self.ple.voucher_no,
				self.ple.against_voucher_type, self.ple.against_voucher_no, self.ple.party_type,
				self.ple.cost_center, self.ple.project, self.ple.party, self.ple.posting_date,
				self.ple.due_date, self.ple.account_currency, self.ple.amount, self.ple.amount_in_account_currency,
			)
			.where(self.ple.delinked == 0)
			.where(Criterion.all(self.qb_selection_filter))
		)

		if self.filters.get("show_remarks"):
			query = query.select(ple.remarks)

		if match_conditions := build_qb_match_conditions("Payment Ledger Entry"):
			query = query.where(Criterion.all(match_conditions))

		if self.filters.get("group_by_party"):
			query = query.orderby(self.ple.party, self.ple.posting_date)
		else:
			query = query.orderby(self.ple.posting_date, self.ple.party)

		self.ple_query = query

	def prepare_conditions(self):
		self.qb_selection_filter = []
		self.add_common_filters()
		
		# CRITICAL FIX: Explicitly requiring 'Employee' records in selection conditions
		self.qb_selection_filter.append(self.ple.party_type == "Employee")
		# Employee AP entries also use Employee as the party type. Restrict the
		# linked ledger account so this report can only return Employee AR entries.
		self.qb_selection_filter.append(self.account.account_type == self.account_type)

		if self.filters.cost_center:
			self.get_cost_center_conditions()

		if self.filters.project:
			self.qb_selection_filter.append(self.ple.project.isin(self.filters.project))

		self.add_user_permission_filters()
		self.add_accounting_dimensions_filters()

	def add_user_permission_filters(self):
		from frappe.core.doctype.user_permission.user_permission import get_user_permissions
		from frappe.permissions import get_allowed_docs_for_doctype

		user_permissions = get_user_permissions()
		if not user_permissions or "Employee" not in user_permissions:
			return

		allowed_parties = get_allowed_docs_for_doctype(user_permissions["Employee"], "Employee")
		self.qb_selection_filter.append(
			(self.ple.party_type != "Employee") | self.ple.party.isin(allowed_parties or [""])
		)

	def get_cost_center_conditions(self):
		cost_center_list = get_cost_centers_with_children(self.filters.cost_center)
		self.qb_selection_filter.append(self.ple.cost_center.isin(cost_center_list))

	def add_common_filters(self):
		if self.filters.company:
			self.qb_selection_filter.append(self.ple.company == self.filters.company)
		if self.filters.finance_book:
			self.qb_selection_filter.append(self.ple.finance_book == self.filters.finance_book)
		if self.filters.get("party"):
			self.qb_selection_filter.append(self.ple.party.isin(self.filters.party))
		if self.filters.party_account:
			self.qb_selection_filter.append(self.ple.account == self.filters.party_account)

	def add_accounting_dimensions_filters(self):
		accounting_dimensions = get_accounting_dimensions(as_list=False)
		if accounting_dimensions:
			for dimension in accounting_dimensions:
				if self.filters.get(dimension.fieldname):
					if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
						self.filters[dimension.fieldname] = get_dimension_with_children(
							dimension.document_type, self.filters.get(dimension.fieldname)
						)
					self.qb_selection_filter.append(self.ple[dimension.fieldname].isin(self.filters[dimension.fieldname]))

	def get_party_details(self, party):
		# FIXED: Pulled out Employee values directly instead of searching Customer/Supplier Master fields
		if party not in self.party_details:
			name = frappe.db.get_value("Employee", party, "employee_name")
			self.party_details[party] = {"employee_name": name or party}
		return self.party_details[party]

	def get_columns(self):
		self.columns = []
		self.add_column(_("Posting Date"), fieldname="posting_date", fieldtype="Date")
		self.add_column(label=_("Party Type"), fieldname="party_type", fieldtype="Data", width=100)
		self.add_column(label=_("Employee ID"), fieldname="party", fieldtype="Link", options="Employee", width=180)
		self.add_column(label=_("Account"), fieldname="party_account", fieldtype="Link", options="Account", width=180)
		
		# FIXED: Direct column for Employee Full Name mapping
		self.add_column(label=_("Employee Name"), fieldname="employee_name", fieldtype="Data", width=180)

		self.add_column(label=_("Cost Center"), fieldname="cost_center", fieldtype="Data")
		self.add_column(label=_("Project"), fieldname="project", fieldtype="Link", options="Project")
		self.add_column(label=_("Voucher Type"), fieldname="voucher_type", fieldtype="Data")
		self.add_column(label=_("Voucher No"), fieldname="voucher_no", fieldtype="Dynamic Link", options="voucher_type", width=180)
		self.add_column(label=_("Due Date"), fieldname="due_date", fieldtype="Date")

		self.add_column(_("Total Obligation / Advance"), fieldname="invoiced")
		self.add_column(_("Cleared / Paid Amount"), fieldname="paid")
		self.add_column(_("Adjustments / Credits"), fieldname="credit_note")
		self.add_column(_("Outstanding Balance"), fieldname="outstanding")

		self.add_column(label=_("Age (Days)"), fieldname="age", fieldtype="Int", width=80)
		self.setup_ageing_columns()
		self.add_column(label=_("Currency"), fieldname="currency", fieldtype="Link", options="Currency", width=80)

		if self.filters.show_future_payments:
			self.add_column(label=_("Future Reference"), fieldname="future_ref", fieldtype="Data")
			self.add_column(label=_("Future Amount"), fieldname="future_amount")
			self.add_column(label=_("Remaining Balance"), fieldname="remaining_balance")

		if self.filters.show_remarks:
			self.add_column(label=_("Remarks"), fieldname="remarks", fieldtype="Text", width=200)

	def add_column(self, label, fieldname=None, fieldtype="Currency", options=None, width=120):
		if not fieldname:
			fieldname = scrub(label)
		if fieldtype == "Currency":
			options = "currency"
		if fieldtype == "Date":
			width = 90
		self.columns.append(dict(label=label, fieldname=fieldname, fieldtype=fieldtype, options=options, width=width))

	def setup_ageing_columns(self):
		self.ageing_column_labels = []
		ranges = [*self.ranges, _("Above")]
		prev_range_value = 0
		for idx, curr_range_value in enumerate(ranges):
			label = f"{prev_range_value}-{curr_range_value}"
			self.add_column(label=label, fieldname="range" + str(idx + 1))
			self.ageing_column_labels.append(label)
			if curr_range_value.isdigit():
				prev_range_value = cint(curr_range_value) + 1

	def get_chart_data(self):
		precision = self.currency_precision
		rows = []
		for row in self.data:
			row = frappe._dict(row)
			if not cint(row.bold):
				values = [flt(row.get(f"range{i}", None), precision) for i in self.range_numbers]
				rows.append({"values": values})

		self.chart = {
			"data": {"labels": self.ageing_column_labels, "datasets": rows},
			"type": "percentage",
		}

	def get_exchange_rate_revaluations(self):
		je = qb.DocType("Journal Entry")
		results = (
			qb.from_(je).select(je.name)
			.where(
				(je.company == self.filters.company)
				& (je.posting_date.lte(self.filters.report_date))
				& ((je.voucher_type == "Exchange Rate Revaluation") | (je.voucher_type == "Exchange Gain Or Loss"))
			).run()
		)
		self.err_journals = [x[0] for x in results] if results else []
