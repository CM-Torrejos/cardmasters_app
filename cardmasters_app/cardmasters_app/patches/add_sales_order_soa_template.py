from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({"Process Statement Of Accounts": [{
        "fieldname": "custom_soa_statement_number", "fieldtype": "Data", "label": "Statement Number",
        "insert_after": "custom_soa_template", "description": "Optional display number for Sales Order statements. Blank uses this document's name.",
    }]}, update=True)
    name = "CardMasters Sales Order SOA"
    if not frappe.db.exists("SOA Template", name):
        directory = Path(frappe.get_app_path("cardmasters_app", "templates", "soa"))
        frappe.get_doc({
            "doctype": "SOA Template", "template_name": name, "report_type": "Accounts Receivable",
            "data_source": "Sales Orders", "excel_layout": "Sales Order Statement", "enabled": 1, "is_default": 0,
            "html": (directory / "sales_order_reference.html").read_text(),
            "css": (directory / "sales_order_reference.css").read_text(),
            "contact_phone": "09536147692 / 09554867374 / 09973443897",
            "contact_email": "collection@cardmastersph.com / accounting@cardmastersph.com",
            "bank_name": "BDO", "bank_account": "0017-6804-1848", "bank_payee": "Marcommax Enterprises",
            "payment_reminder": "Reminder: Please be reminded that payment should be settled within five (5) working days upon receipt of the Statement of Account (SOA).",
            "prepared_by": "Jayson Brian R. Sinampaga, RC", "prepared_title": "AR Collector",
            "checked_by": "Joemariemar G. Bucar", "checked_title": "Finance Analyst",
        }).insert(ignore_permissions=True)
