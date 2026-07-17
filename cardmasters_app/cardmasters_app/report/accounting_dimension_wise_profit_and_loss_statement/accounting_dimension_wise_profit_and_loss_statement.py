# Copyright (c) 2026, Shan Torrejos and contributors
# License: GNU General Public License v3. See license.txt

from copy import copy
from hashlib import md5

import frappe
from frappe import _
from frappe.utils import flt

from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_dimension_with_children,
	get_dimensions,
)
from erpnext.accounts.report.financial_statements import (
	get_cost_centers_with_children,
	get_data,
	get_period_list,
)
from erpnext.accounts.report.profit_and_loss_statement.profit_and_loss_statement import (
	get_net_profit_loss,
	get_report_summary,
)


def execute(filters=None):
	filters = frappe._dict(filters or {})
	validate_filters(filters)

	period_list = get_period_list(
		filters.from_fiscal_year,
		filters.to_fiscal_year,
		filters.period_start_date,
		filters.period_end_date,
		filters.filter_based_on,
		filters.periodicity,
		company=filters.company,
	)

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	base_income, base_expense, base_net_profit_loss = get_profit_and_loss_data(filters, period_list)
	dimension = get_selected_dimension(filters.selected_dimension)
	dimension_values = get_dimension_values(filters, dimension, period_list)
	dimension_columns = get_dimension_columns(dimension_values)

	income = get_dimension_wise_rows(
		base_income,
		"Income",
		"Credit",
		filters,
		period_list,
		dimension,
		dimension_columns,
		currency,
	)
	expense = get_dimension_wise_rows(
		base_expense,
		"Expense",
		"Debit",
		filters,
		period_list,
		dimension,
		dimension_columns,
		currency,
	)
	net_profit_loss = get_dimension_wise_net_profit_loss(
		base_net_profit_loss, income, expense, filters, period_list, dimension_columns, currency
	)

	data = []
	data.extend(income or [])
	data.extend(expense or [])
	if net_profit_loss:
		data.append(net_profit_loss)

	columns = get_columns(filters.company, dimension_columns)
	chart = get_chart_data(filters.company, dimension_columns, income, expense, net_profit_loss, currency)
	report_summary, primitive_summary = get_report_summary(
		period_list, filters.periodicity, base_income, base_expense, base_net_profit_loss, currency, filters
	)

	return columns, data, None, chart, report_summary, primitive_summary


def validate_filters(filters):
	if not filters.company:
		frappe.throw(_("Company is mandatory"))

	if not filters.selected_dimension:
		dimensions = get_available_dimensions()
		if dimensions:
			filters.selected_dimension = dimensions[0].fieldname
		else:
			frappe.throw(_("No accounting dimensions are enabled"))

	if filters.filter_based_on == "Fiscal Year":
		if not filters.from_fiscal_year or not filters.to_fiscal_year:
			frappe.throw(_("Start Year and End Year are mandatory"))
	elif not filters.period_start_date or not filters.period_end_date:
		frappe.throw(_("Start Date and End Date are mandatory"))


def get_profit_and_loss_data(filters, period_list):
	income = get_data(
		filters.company,
		"Income",
		"Credit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)
	expense = get_data(
		filters.company,
		"Expense",
		"Debit",
		period_list,
		filters=filters,
		accumulated_values=filters.accumulated_values,
		ignore_closing_entries=True,
	)
	net_profit_loss = get_net_profit_loss(
		income, expense, period_list, filters.company, filters.presentation_currency
	)

	return income, expense, net_profit_loss


def get_selected_dimension(fieldname):
	for dimension in get_available_dimensions():
		if dimension.fieldname == fieldname:
			return dimension

	frappe.throw(_("Invalid accounting dimension: {0}").format(fieldname))


def get_available_dimensions():
	dimensions = get_dimensions(with_cost_center_and_project=True)[0]
	for dimension in dimensions:
		if not dimension.get("label"):
			dimension.label = dimension.document_type

	return dimensions


def get_dimension_values(filters, dimension, period_list):
	selected_values = filters.get("dimension_values") or []
	if isinstance(selected_values, str):
		selected_values = frappe.parse_json(selected_values)

	if selected_values:
		return selected_values

	return get_distinct_dimension_values(filters, dimension, period_list)


def get_distinct_dimension_values(filters, dimension, period_list):
	fieldname = dimension.fieldname
	from_date = period_list[0]["year_start_date"]
	to_date = period_list[-1]["to_date"]

	conditions = [
		"gle.company = %(company)s",
		"gle.is_cancelled = 0",
		"gle.posting_date >= %(from_date)s",
		"gle.posting_date <= %(to_date)s",
		"gle.voucher_type != 'Period Closing Voucher'",
		f"ifnull(gle.`{fieldname}`, '') != ''",
		"acc.root_type in ('Income', 'Expense')",
	]
	params = {
		"company": filters.company,
		"from_date": from_date,
		"to_date": to_date,
	}

	if filters.get("finance_book"):
		conditions.append("(gle.finance_book in (%(finance_book)s, '') or gle.finance_book is null)")
		params["finance_book"] = filters.finance_book

	values = frappe.db.sql(
		f"""
		select distinct gle.`{fieldname}` as value
		from `tabGL Entry` gle
		inner join `tabAccount` acc on acc.name = gle.account
		where {" and ".join(conditions)}
		order by gle.`{fieldname}`
		""",
		params,
		as_dict=True,
	)

	return [value.value for value in values]


def get_dimension_columns(dimension_values):
	columns = []
	used_fieldnames = set()

	for value in dimension_values:
		fieldname = "dimension_" + md5(value.encode()).hexdigest()[:10]
		while fieldname in used_fieldnames:
			fieldname = "dimension_" + md5(f"{value}-{len(used_fieldnames)}".encode()).hexdigest()[:10]

		used_fieldnames.add(fieldname)
		columns.append(frappe._dict({"fieldname": fieldname, "label": value, "value": value}))

	return columns


def get_dimension_wise_rows(
	base_rows,
	root_type,
	balance_must_be,
	filters,
	period_list,
	dimension,
	dimension_columns,
	currency,
):
	rows = prepare_base_rows(base_rows, period_list, currency, filters.accumulated_values)

	for dimension_column in dimension_columns:
		dimension_filters = get_filters_for_dimension(filters, dimension, dimension_column.value)
		dimension_rows = get_data(
			dimension_filters.company,
			root_type,
			balance_must_be,
			period_list,
			filters=dimension_filters,
			accumulated_values=dimension_filters.accumulated_values,
			ignore_closing_entries=True,
		)
		values_by_account = get_values_by_account(dimension_rows, period_list, filters.accumulated_values)

		for row in rows:
			account = row.get("account")
			if account:
				row[dimension_column.fieldname] = values_by_account.get(account, 0.0)

	return rows


def prepare_base_rows(base_rows, period_list, currency, accumulated_values):
	rows = []
	for base_row in base_rows or []:
		row = frappe._dict(copy(base_row))

		for period in period_list:
			row.pop(period.key, None)

		row["company_total"] = get_row_amount(base_row, period_list, accumulated_values)
		row["total"] = row["company_total"]
		row["currency"] = currency
		rows.append(row)

	return rows


def get_values_by_account(rows, period_list, accumulated_values):
	values = {}
	for row in rows or []:
		account = row.get("account")
		if account:
			values[account] = get_row_amount(row, period_list, accumulated_values)

	return values


def get_row_amount(row, period_list, accumulated_values):
	if not row:
		return 0.0

	if accumulated_values:
		return flt(row.get(period_list[-1].key), 3)

	return flt(row.get("total", sum(flt(row.get(period.key)) for period in period_list)), 3)


def get_filters_for_dimension(filters, dimension, value):
	dimension_filters = frappe._dict(copy(filters))
	dimension_filters[dimension.fieldname] = get_dimension_filter_values(dimension, value)
	return dimension_filters


def get_dimension_filter_values(dimension, value):
	if dimension.document_type == "Cost Center":
		return get_cost_centers_with_children(value)

	if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
		return get_dimension_with_children(dimension.document_type, value)

	return [value]


def get_dimension_wise_net_profit_loss(
	base_net_profit_loss, income, expense, filters, period_list, dimension_columns, currency
):
	if not base_net_profit_loss:
		return None

	net_profit_loss = frappe._dict(copy(base_net_profit_loss))

	for period in period_list:
		net_profit_loss.pop(period.key, None)

	net_profit_loss["company_total"] = get_row_amount(
		base_net_profit_loss, period_list, filters.accumulated_values
	)
	net_profit_loss["total"] = net_profit_loss["company_total"]
	net_profit_loss["currency"] = currency

	income_total = get_total_row(income)
	expense_total = get_total_row(expense)
	has_value = bool(net_profit_loss.get("company_total"))

	for dimension_column in dimension_columns:
		value = flt(income_total.get(dimension_column.fieldname)) - flt(
			expense_total.get(dimension_column.fieldname)
		)
		net_profit_loss[dimension_column.fieldname] = value
		has_value = has_value or bool(value)

	return net_profit_loss if has_value else None


def get_total_row(rows):
	for row in reversed(rows or []):
		if row.get("account"):
			return row

	return frappe._dict()


def get_columns(company, dimension_columns):
	columns = [
		{
			"fieldname": "account",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Account",
			"width": 300,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
		{
			"fieldname": "company_total",
			"label": company,
			"fieldtype": "Currency",
			"options": "currency",
			"width": 150,
		},
	]

	for dimension_column in dimension_columns:
		columns.append(
			{
				"fieldname": dimension_column.fieldname,
				"label": dimension_column.label,
				"fieldtype": "Currency",
				"options": "currency",
				"width": 150,
			}
		)

	return columns


def get_chart_data(company, dimension_columns, income, expense, net_profit_loss, currency):
	chart_columns = [frappe._dict({"fieldname": "company_total", "label": company})] + dimension_columns
	income_total = get_total_row(income)
	expense_total = get_total_row(expense)

	datasets = []
	if income:
		datasets.append(
			{"name": _("Income"), "values": [income_total.get(column.fieldname) for column in chart_columns]}
		)
	if expense:
		datasets.append(
			{"name": _("Expense"), "values": [expense_total.get(column.fieldname) for column in chart_columns]}
		)
	if net_profit_loss:
		datasets.append(
			{
				"name": _("Net Profit/Loss"),
				"values": [net_profit_loss.get(column.fieldname) for column in chart_columns],
			}
		)

	return {
		"data": {"labels": [column.label for column in chart_columns], "datasets": datasets},
		"type": "bar",
		"fieldtype": "Currency",
		"options": "currency",
		"currency": currency,
	}
