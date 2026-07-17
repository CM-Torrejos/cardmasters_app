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
from erpnext.accounts.report.balance_sheet.balance_sheet import (
	check_opening_balance,
	get_provisional_profit_loss,
	get_report_summary,
)
from erpnext.accounts.report.financial_statements import (
	get_cost_centers_with_children,
	get_data,
	get_period_list,
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
	filters.period_start_date = period_list[0]["year_start_date"]

	currency = filters.presentation_currency or frappe.get_cached_value(
		"Company", filters.company, "default_currency"
	)

	base_asset, base_liability, base_equity = get_balance_sheet_data(filters, period_list)
	base_provisional_profit_loss, base_total_credit = get_provisional_profit_loss(
		base_asset, base_liability, base_equity, period_list, filters.company, currency
	)
	message, base_opening_balance = check_opening_balance(base_asset, base_liability, base_equity)

	dimension = get_selected_dimension(filters.selected_dimension)
	dimension_values = get_dimension_values(filters, dimension, period_list)
	dimension_columns = get_dimension_columns(dimension_values)
	dimension_data = get_dimension_data(filters, period_list, dimension, dimension_columns, currency)

	asset = get_dimension_wise_rows(
		base_asset, dimension_columns, dimension_data, "asset", period_list, currency, filters.accumulated_values
	)
	liability = get_dimension_wise_rows(
		base_liability,
		dimension_columns,
		dimension_data,
		"liability",
		period_list,
		currency,
		filters.accumulated_values,
	)
	equity = get_dimension_wise_rows(
		base_equity, dimension_columns, dimension_data, "equity", period_list, currency, filters.accumulated_values
	)

	unclosed = get_unclosed_fiscal_year_row(
		base_opening_balance, dimension_columns, dimension_data, currency
	)
	provisional_profit_loss = get_dimension_wise_provisional_profit_loss(
		base_provisional_profit_loss,
		base_opening_balance,
		dimension_columns,
		dimension_data,
		period_list,
		currency,
		filters.accumulated_values,
	)
	total_credit = get_dimension_wise_total_credit(
		base_total_credit, dimension_columns, dimension_data, period_list, currency, filters.accumulated_values
	)

	data = []
	data.extend(asset or [])
	data.extend(liability or [])
	data.extend(equity or [])
	if unclosed:
		data.append(unclosed)
	if provisional_profit_loss:
		data.append(provisional_profit_loss)
	if total_credit:
		data.append(total_credit)

	columns = get_columns(filters.company, dimension_columns)
	chart = get_chart_data(filters.company, dimension_columns, asset, liability, equity, currency)
	report_summary, primitive_summary = get_report_summary(
		period_list,
		base_asset,
		base_liability,
		base_equity,
		base_provisional_profit_loss,
		currency,
		filters,
	)

	return columns, data, message, chart, report_summary, primitive_summary


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


def get_balance_sheet_data(filters, period_list):
	asset = get_data(
		filters.company,
		"Asset",
		"Debit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)
	liability = get_data(
		filters.company,
		"Liability",
		"Credit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)
	equity = get_data(
		filters.company,
		"Equity",
		"Credit",
		period_list,
		only_current_fiscal_year=False,
		filters=filters,
		accumulated_values=filters.accumulated_values,
	)

	return asset, liability, equity


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
	to_date = period_list[-1]["to_date"]

	conditions = [
		"gle.company = %(company)s",
		"gle.is_cancelled = 0",
		"gle.posting_date <= %(to_date)s",
		f"ifnull(gle.`{fieldname}`, '') != ''",
		"acc.root_type in ('Asset', 'Liability', 'Equity')",
	]
	params = {
		"company": filters.company,
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


def get_dimension_data(filters, period_list, dimension, dimension_columns, currency):
	dimension_data = {}

	for dimension_column in dimension_columns:
		dimension_filters = get_filters_for_dimension(filters, dimension, dimension_column.value)
		asset, liability, equity = get_balance_sheet_data(dimension_filters, period_list)
		provisional_profit_loss, total_credit = get_provisional_profit_loss(
			asset, liability, equity, period_list, filters.company, currency
		)
		_, opening_balance = check_opening_balance(asset, liability, equity)

		dimension_data[dimension_column.fieldname] = frappe._dict(
			{
				"asset": asset,
				"liability": liability,
				"equity": equity,
				"provisional_profit_loss": provisional_profit_loss,
				"total_credit": total_credit,
				"opening_balance": opening_balance,
			}
		)

	return dimension_data


def get_dimension_wise_rows(
	base_rows, dimension_columns, dimension_data, section, period_list, currency, accumulated_values
):
	rows = prepare_base_rows(base_rows, period_list, currency, accumulated_values)

	for dimension_column in dimension_columns:
		values_by_account = get_values_by_account(
			dimension_data.get(dimension_column.fieldname, {}).get(section),
			period_list,
			accumulated_values,
		)

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


def get_unclosed_fiscal_year_row(base_opening_balance, dimension_columns, dimension_data, currency):
	has_value = bool(base_opening_balance and round(base_opening_balance, 2) != 0)
	if not has_value and not dimension_columns:
		return None

	row = frappe._dict(
		{
			"account_name": "'" + _("Unclosed Fiscal Years Profit / Loss (Credit)") + "'",
			"account": "'" + _("Unclosed Fiscal Years Profit / Loss (Credit)") + "'",
			"warn_if_negative": True,
			"currency": currency,
			"company_total": base_opening_balance or 0.0,
			"total": base_opening_balance or 0.0,
		}
	)

	for dimension_column in dimension_columns:
		opening_balance = dimension_data.get(dimension_column.fieldname, {}).get("opening_balance") or 0.0
		row[dimension_column.fieldname] = opening_balance
		has_value = has_value or bool(opening_balance and round(opening_balance, 2) != 0)

	return row if has_value else None


def get_dimension_wise_provisional_profit_loss(
	base_provisional_profit_loss,
	base_opening_balance,
	dimension_columns,
	dimension_data,
	period_list,
	currency,
	accumulated_values,
):
	if not base_provisional_profit_loss:
		return None

	row = prepare_special_row(base_provisional_profit_loss, period_list, currency, accumulated_values)
	row.company_total = flt(row.company_total) - flt(base_opening_balance)
	row.total = row.company_total
	has_value = bool(row.company_total)

	for dimension_column in dimension_columns:
		dimension_row = dimension_data.get(dimension_column.fieldname, {}).get("provisional_profit_loss")
		opening_balance = dimension_data.get(dimension_column.fieldname, {}).get("opening_balance") or 0.0
		value = get_row_amount(dimension_row, period_list, accumulated_values) - flt(opening_balance)
		row[dimension_column.fieldname] = value
		has_value = has_value or bool(value)

	return row if has_value else None


def get_dimension_wise_total_credit(
	base_total_credit, dimension_columns, dimension_data, period_list, currency, accumulated_values
):
	if not base_total_credit:
		return None

	row = prepare_special_row(base_total_credit, period_list, currency, accumulated_values)
	has_value = bool(row.company_total)

	for dimension_column in dimension_columns:
		dimension_row = dimension_data.get(dimension_column.fieldname, {}).get("total_credit")
		value = get_row_amount(dimension_row, period_list, accumulated_values)
		row[dimension_column.fieldname] = value
		has_value = has_value or bool(value)

	return row if has_value else None


def prepare_special_row(base_row, period_list, currency, accumulated_values):
	row = frappe._dict(copy(base_row))

	for period in period_list:
		row.pop(period.key, None)

	row["company_total"] = get_row_amount(base_row, period_list, accumulated_values)
	row["total"] = row["company_total"]
	row["currency"] = currency
	return row


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


def get_chart_data(company, dimension_columns, asset, liability, equity, currency):
	chart_columns = [frappe._dict({"fieldname": "company_total", "label": company})] + dimension_columns
	asset_total = get_total_row(asset)
	liability_total = get_total_row(liability)
	equity_total = get_total_row(equity)

	datasets = []
	if asset:
		datasets.append(
			{"name": _("Assets"), "values": [asset_total.get(column.fieldname) for column in chart_columns]}
		)
	if liability:
		datasets.append(
			{
				"name": _("Liabilities"),
				"values": [liability_total.get(column.fieldname) for column in chart_columns],
			}
		)
	if equity:
		datasets.append(
			{"name": _("Equity"), "values": [equity_total.get(column.fieldname) for column in chart_columns]}
		)

	return {
		"data": {"labels": [column.label for column in chart_columns], "datasets": datasets},
		"type": "bar",
		"fieldtype": "Currency",
		"options": "currency",
		"currency": currency,
	}


def get_total_row(rows):
	for row in reversed(rows or []):
		if row.get("account"):
			return row

	return frappe._dict()
