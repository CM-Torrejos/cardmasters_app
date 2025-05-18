// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.query_reports["Sales ➔ Work ➔ Job Card"] = {
	formatter: function(value, row, column, data, default_formatter) {
	  // base rendering (including the link)
	  let v = default_formatter(value, row, column, data);
  
	  // Sales Order: add status if present
	  if (column.fieldname === "sales_order" && data.sales_order_status) {
		v = `${v} (${data.sales_order_status})`;
	  }
  
	  // Work Order: indent when SO is blank, then add status
	  if (column.fieldname === "work_order") {
		let pad = !data.sales_order ? "padding-left:1.5em;" : "";
		let txt = v;
		if (data.work_order_status) {
		  txt = `${txt} (${data.work_order_status})`;
		}
		return `<div style="${pad}">${txt}</div>`;
	  }
  
	  // Job Card: always indented deeper + add status
	  if (column.fieldname === "job_card") {
		let txt = v;
		if (data.job_card_status) {
		  txt = `${txt} (${data.job_card_status})`;
		}
		return `<div style="padding-left:3em;">${txt}</div>`;
	  }
  
	  return v;
	}
  };
  