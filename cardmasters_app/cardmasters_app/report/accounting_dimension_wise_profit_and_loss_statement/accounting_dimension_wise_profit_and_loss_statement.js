// Copyright (c) 2026, Shan Torrejos and contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Accounting Dimension-wise Profit and Loss Statement"] = $.extend(
	{},
	erpnext.financial_statements
);

frappe.query_reports["Accounting Dimension-wise Profit and Loss Statement"].filters =
	erpnext.financial_statements.filters
		.filter((filter) => !["cost_center", "project"].includes(filter.fieldname))
		.map((filter) => Object.assign({}, filter));

frappe.query_reports["Accounting Dimension-wise Profit and Loss Statement"].filters.push(
	{
		fieldname: "selected_dimension",
		label: __("Accounting Dimension"),
		fieldtype: "Select",
		reqd: 1,
		on_change: function () {
			frappe.query_report.set_filter_value("dimension_values", []);
		},
	},
	{
		fieldname: "dimension_values",
		label: __("Dimension Values"),
		fieldtype: "MultiSelectList",
		get_data: function (txt) {
			const report = frappe.query_reports["Accounting Dimension-wise Profit and Loss Statement"];
			const selected_dimension = frappe.query_report.get_filter_value("selected_dimension");
			const dimension = report.accounting_dimensions?.[selected_dimension];

			if (!dimension) {
				return [];
			}

			const filters =
				dimension.document_type === "Cost Center"
					? { company: frappe.query_report.get_filter_value("company") }
					: {};

			return frappe.db.get_link_options(dimension.document_type, txt, filters);
		},
	},
	{
		fieldname: "accumulated_values",
		label: __("Accumulated Values"),
		fieldtype: "Check",
		default: 0,
	},
	{
		fieldname: "include_default_book_entries",
		label: __("Include Default FB Entries"),
		fieldtype: "Check",
		default: 1,
	},
	{
		fieldname: "show_zero_values",
		label: __("Show zero values"),
		fieldtype: "Check",
	}
);

frappe.query_reports["Accounting Dimension-wise Profit and Loss Statement"].onload = function (report) {
	erpnext.financial_statements.onload(report);

	frappe.call({
		method: "erpnext.accounts.doctype.accounting_dimension.accounting_dimension.get_dimensions",
		args: {
			with_cost_center_and_project: 1,
		},
		callback: function (r) {
			const dimensions = r.message?.[0] || [];
			const options = [];

			report.accounting_dimensions = {};

			dimensions.forEach((dimension) => {
				const label = dimension.label || dimension.document_type;
				report.accounting_dimensions[dimension.fieldname] = {
					label: label,
					document_type: dimension.document_type,
				};
				options.push({ label: __(label), value: dimension.fieldname });
			});

			const filter = report.get_filter("selected_dimension");
			filter.df.options = options;
			filter.refresh();

			if (!filter.get_value() && options.length) {
				frappe.query_report.set_filter_value("selected_dimension", options[0].value);
			}
		},
	});
};
