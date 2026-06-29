// Copyright (c) 2026, Your Company and Contributors
// License: GNU General Public License v3. See license.txt

frappe.provide("erpnext.utils");

// Note: Ensure the string name here exactly matches your Report name in the DB
frappe.query_reports["Employee Accounts Receivable"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "report_date",
			label: __("Posting Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "finance_book",
			label: __("Finance Book"),
			fieldtype: "Link",
			options: "Finance Book",
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "MultiSelectList",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
			options: "Cost Center",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "MultiSelectList",
			options: "Project",
			get_data: function (txt) {
				return frappe.db.get_link_options("Project", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
		},
		{
			// Changed from dynamic party selection to a direct Employee link
			fieldname: "party",
			label: __("Employee"),
			fieldtype: "MultiSelectList",
			options: "Employee",
		},
		{
			fieldname: "party_account",
			label: __("Receivable/Log Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: () => {
				var company = frappe.query_report.get_filter_value("company");
				return {
					filters: {
						company: company,
						is_group: 0,
					},
				};
			},
		},
		{
			fieldname: "ageing_based_on",
			label: __("Ageing Based On"),
			fieldtype: "Select",
			options: "Posting Date\nDue Date",
			default: "Posting Date",
		},
		{
			fieldname: "calculate_ageing_with",
			label: __("Calculate Ageing With"),
			fieldtype: "Select",
			options: "Report Date\nToday Date",
			default: "Report Date",
		},
		{
			fieldname: "range",
			label: __("Ageing Range"),
			fieldtype: "Data",
			default: "30, 60, 90, 120",
		},
		{
			fieldname: "group_by_party",
			label: __("Group By Employee"),
			fieldtype: "Check",
		},
		{
			fieldname: "show_remarks",
			label: __("Show Remarks"),
			fieldtype: "Check",
		},
		{
			fieldname: "for_revaluation_journals",
			label: __("Revaluation Journals"),
			fieldtype: "Check",
		},
		{
			fieldname: "ignore_accounts",
			label: __("Group by Voucher"),
			fieldtype: "Check",
		},
		{
			fieldname: "in_party_currency",
			label: __("In Employee Currency"),
			fieldtype: "Check",
		},
	],

	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.bold) {
			value = value.bold();
		}
		return value;
	},

	onload: function (report) {
		if (frappe.boot.sysdefaults.default_ageing_range) {
			report.set_filter_value("range", frappe.boot.sysdefaults.default_ageing_range);
		}

		report.page.add_inner_button(__("Reclassify to Employee AR"), function() {
			frappe.confirm(
				__('Are you sure you want to run batch reclassification? An Excel-compatible audit spreadsheet log will be generated automatically at the end.'), 
				function() {
					
					let current_filters = report.get_values();

					frappe.show_progress(__("Processing Reclassification"), 0, 100, __("Querying core Accounts Receivable report context..."));

					frappe.realtime.on("reclass_progress", function(data) {
						frappe.show_progress(__("Processing Reclassification"), data.current, data.total, data.message);
					});

					frappe.call({
						method: "cardmasters_app.cardmasters_app.api.employee_ar_reclassification.run_employee_ar_reclassification",
						args: {
							filters: current_filters
						},
						callback: function(r) {
							if (!r.exc && r.message) {
								
								// Central validation dialog layout response
								frappe.msgprint({
									title: __('Reclassification Run Complete'),
									indicator: r.message.status === 'complete' ? 'green' : 'orange',
									message: r.message.message
								});

								// TRIGGER DOWNLOAD: If a file URL was compiled, launch the download stream
								if (r.message.file_url) {
									window.open(r.message.file_url, '_blank');
								}

								report.refresh();
							}
						},
						always: function() {
							frappe.realtime.off("reclass_progress");
							frappe.hide_progress();
						}
					});
				}
			);
		});
	},
};

// Adjust dimension configuration to hook your custom report layout
erpnext.utils.add_dimensions("Employee Accounts Receivable", 6);