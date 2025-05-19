# Server Script: Sales Order – Before Save
# Deletes old sheets (unless coming from Production)
# then auto-creates a new Artist Sheet when status is ARTIST – {First Last}

# your_app/sales_order.py

import frappe
from frappe.utils import nowdate

def handle_progress_status(doc, method):

    old_status = frappe.db.get_value("Sales Order",
                                     doc.name,
                                     "custom_progress_status") or ""
    new_status = doc.custom_progress_status or ""

    # only do anything when landing in an ARTIST column
    if not new_status.startswith("ARTIST"):
        return

    # if we didn’t come from PRODUCTION, purge any existing sheet
    if old_status != "PRODUCTION":
        for sheet_name in frappe.get_all("Artist Sheet",
                                         filters={"sales_order": doc.name},
                                         pluck="name"):
            frappe.delete_doc("Artist Sheet", sheet_name, force=True)

        # now *always* create a new one (so Artist→Artist works immediately)
        _, fullname = new_status.split(" - ", 1)
        parts = fullname.split(" ", 1)
        first, last = parts[0], parts[1] if len(parts) > 1 else ""

        emp = frappe.db.get_value("Employee",
                                  {"first_name": first, "last_name": last},
                                  "name")
        if emp:
            frappe.get_doc({
                "doctype": "Artist Sheet",
                "sales_order": doc.name,
                "artist": emp,
                "date_created": nowdate()
            }).insert(ignore_permissions=True)
