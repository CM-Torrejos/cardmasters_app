// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.query_reports["Artist Monitoring"] = {
	"filters": [
		{
			"fieldname": "status",
			"fieldtype": "Select",
			"label": "Status",
			"mandatory": 0,
			"options": "pending\nfinished",
			"wildcard_filter": 0
			},
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
