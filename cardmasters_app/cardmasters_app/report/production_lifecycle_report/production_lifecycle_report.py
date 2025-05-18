# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

# import frappe

import frappe

def execute(filters=None):
    columns = [
        {"label":"Sales Order", "fieldname":"sales_order", "fieldtype":"Link", "options":"Sales Order", "width":200},
        {"label":"Work Order",  "fieldname":"work_order",  "fieldtype":"Link", "options":"Work Order",  "width":200},
        {"label":"Job Card",    "fieldname":"job_card",    "fieldtype":"Link", "options":"Job Card",    "width":200},
    ]

    data = []
    for so in frappe.get_all("Sales Order", fields=["name","status"]):
        first_so_row = True
        work_orders = frappe.get_all("Work Order", fields=["name","status"], filters={"sales_order": so.name})
        for wo in work_orders:
            job_cards = frappe.get_all("Job Card", fields=["name","status"], filters={"work_order": wo.name})
            for idx, jc in enumerate(job_cards):
                row = {}
                # only show SO name & status on the very first JC row
                if first_so_row and idx == 0:
                    row["sales_order"] = so.name
                    row["sales_order_status"] = so.status
                    first_so_row = False
                # only show WO name & status on its first JC
                if idx == 0:
                    row["work_order"] = wo.name
                    row["work_order_status"] = wo.status
                # always show JC name & status
                row["job_card"] = jc.name
                row["job_card_status"] = jc.status

                data.append(row)

    return columns, data
