// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.query_reports["Artist Performance Monitoring"] = {
	"filters": [
		{
			"fieldname": "from_date",
			"fieldtype": "Date",
			"label": "From Date",
			"mandatory": 0,
			"wildcard_filter": 0
  			},
		{
			"fieldname": "to_date",
			"fieldtype": "Date",
			"label": "To Date",
			"mandatory": 0,
			"wildcard_filter": 0
		   },
	]
};
