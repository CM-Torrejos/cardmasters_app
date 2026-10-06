from pathlib import Path

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({"Process Statement Of Accounts": [{
        "fieldname": "custom_soa_template", "fieldtype": "Link", "label": "SOA Template",
        "options": "SOA Template", "insert_after": "letter_head",
        "description": "Choose an editable HTML/CSS layout. Blank uses the report's default template, or the native layout if no default exists.",
    }]}, update=True)
    directory = Path(frappe.get_app_path("cardmasters_app", "templates", "soa"))
    for report_type in ("General Ledger", "Accounts Receivable"):
        name = f"CardMasters {report_type}"
        if not frappe.db.exists("SOA Template", name):
            frappe.get_doc({
                "doctype": "SOA Template", "template_name": name, "report_type": report_type,
                "enabled": 1, "is_default": 0,
                "html": (directory / "starter.html").read_text(),
                "css": (directory / "starter.css").read_text(),
            }).insert(ignore_permissions=True)
