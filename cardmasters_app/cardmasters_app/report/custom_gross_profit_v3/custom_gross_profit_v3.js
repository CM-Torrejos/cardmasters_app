// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Custom Gross Profit v3"] = {
	onload: function (report) {
		if (!frappe.model.can_export(report.report_doc.ref_doctype)) return;
		report.page.add_inner_button(__("Export Machine-readable CSV"), () => {
			if (!frappe.model.can_export(report.report_doc.ref_doctype)) return;
			if (!report.data || !report.data.length) {
				frappe.msgprint(__("Run the report before exporting."));
				return;
			}
			const export_rows = this.get_flat_export_rows(report.data);
			const fields = [...new Set([
				"sales_invoice", "item_code", "item_name", "manufacture_entry",
				"component_item_code", "component_item_name", "manufacturing_breakdown",
				"source_stock_entry", "work_order", "row_type", "currency",
				...report.columns.map((column) => column.fieldname)
					.filter((field) => field && !["indent", "report_row_id", "parent_row_id"].includes(field)),
			])];
			const csv_cell = (value) => {
				const text = value == null ? "" : String(value);
				return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
			};
			const rows = export_rows.map((row) => fields.map((field) => row[field]));
			const csv = [fields, ...rows].map((row) => row.map(csv_cell).join(",")).join("\r\n");
			const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
			const link = document.createElement("a");
			link.href = url;
			link.download = "custom_gross_profit_v3.csv";
			document.body.appendChild(link);
			link.click();
			link.remove();
			setTimeout(() => URL.revokeObjectURL(url), 1000);
			report.make_access_log("Export", "CSV");
		});
	},
	get_flat_export_rows: function (data) {
		const by_id = new Map(data.filter((row) => row.report_row_id)
			.map((row) => [row.report_row_id, row]));
		return data.map((row) => {
			const ancestry = [];
			const visited = new Set();
			let ancestor = row;
			while (ancestor && !visited.has(ancestor)) {
				visited.add(ancestor);
				ancestry.push(ancestor);
				ancestor = by_id.get(ancestor.parent_row_id);
			}
			const invoice = ancestry.find((parent) => parent.row_type === "invoice");
			const item = ancestry.find((parent) => parent.row_type === "item");
			const manufacture = ancestry.find((parent) => parent.row_type === "manufacture");
			const is_component = ["material", "scrap"].includes(row.row_type);
			const is_breakdown = row.row_type && !["invoice", "item"].includes(row.row_type);
			return {
				...row,
				row_type: row.row_type || (row.sales_invoice === "Total" ? "total" : "group"),
				sales_invoice: invoice ? invoice.sales_invoice : (row.row_type ? "" : row.sales_invoice),
				item_code: item ? (item.item_code || item.sales_invoice) : row.item_code,
				item_name: item ? item.item_name : (is_component ? "" : row.item_name),
				manufacture_entry: manufacture ? manufacture.manufacture_entry : row.manufacture_entry,
				component_item_code: is_component ? row.sales_invoice : "",
				component_item_name: is_component ? row.item_name : "",
				manufacturing_breakdown: is_breakdown ? row.sales_invoice : "",
				source_stock_entry: is_breakdown ? row.manufacture_entry : "",
				work_order: row.work_order || (manufacture && manufacture.work_order),
			};
		});
	},
	filters: [
		{
			fieldname: "show_cost_breakdown",
			label: __("Show Manufacturing Cost Breakdown"),
			fieldtype: "Check",
			default: 1,
			depends_on: "eval:doc.group_by == 'Invoice'",
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
			reqd: 1,
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[1],
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: erpnext.utils.get_fiscal_year(frappe.datetime.get_today(), true)[2],
			reqd: 1,
		},
		{
			fieldname: "sales_invoice",
			label: __("Sales Invoice"),
			fieldtype: "Link",
			options: "Sales Invoice",
		},
		{
			fieldname: "group_by",
			label: __("Group By"),
			fieldtype: "Select",
			options:
				"Invoice\nItem Code\nItem Group\nBrand\nWarehouse\nCustomer\nCustomer Group\nTerritory\nSales Person\nProject\nCost Center\nMonthly\nPayment Term",
			default: "Invoice",
		},
		{
			fieldname: "item_group",
			label: __("Item Group"),
			fieldtype: "Link",
			options: "Item Group",
		},
		{
			fieldname: "sales_person",
			label: __("Sales Person"),
			fieldtype: "Link",
			options: "Sales Person",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse"),
			fieldtype: "Link",
			options: "Warehouse",
			get_query: function () {
				var company = frappe.query_report.get_filter_value("company");
				return {
					filters: [["Warehouse", "company", "=", company]],
				};
			},
		},
		{
			fieldname: "cost_center",
			label: __("Cost Center"),
			fieldtype: "MultiSelectList",
			options: "Cost Center",
			get_data: function (txt) {
				return frappe.db.get_link_options("Cost Center", txt, {
					company: frappe.query_report.get_filter_value("company"),
				});
			},
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
			fieldname: "include_returned_invoices",
			label: __("Include Returned Invoices (Stand-alone)"),
			fieldtype: "Check",
			default: 1,
		},
	],
	tree: true,
	name_field: "report_row_id",
	parent_field: "parent_row_id",
	initial_depth: 2,
	formatter: function (value, row, column, data, default_formatter) {
		if (column.fieldname == "sales_invoice") {
			column._options = data && data.row_type === "invoice" ? "Sales Invoice"
				: data && ["item", "material", "scrap"].includes(data.row_type) ? "Item" : "";
		}
		value = default_formatter(value, row, column, data);

		if (data && (data.indent == 0.0 || (row[1] && row[1].content == "Total"))) {
			value = $(`<span>${value}</span>`);
			var $value = $(value).css("font-weight", "bold");
			value = $value.wrap("<p></p>").parent().html();
		}

		return value;
	},
};

erpnext.utils.add_dimensions("Custom Gross Profit v3", 15);
