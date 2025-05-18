# Server Script: Sales Order – Before Save
# Deletes old sheets (unless coming from Production)
# then auto-creates a new Artist Sheet when status is ARTIST – {First Last}

import frappe
from frappe.utils import nowdate


def before_save(doc, method):
    # fetch the *old* status from the database
    old_status = frappe.db.get_value("Sales Order", doc.name, "custom_progress_status") or ""

    new_status = doc.custom_progress_status or ""
    if new_status.startswith("ARTIST"):
        # 1) delete any existing sheet if we weren't sent back from Production
        if old_status != "PRODUCTION" or old_status != "PENDING":
            for sheet_name in frappe.get_all("Artist Sheet",
                                            filters={"sales_order": doc.name},
                                            pluck="name"):
                frappe.delete_doc("Artist Sheet", sheet_name, force=True)

        # 2) only create *if none* exists (so we don't duplicate on PRODUCTION→ARTIST)
        if not frappe.db.exists("Artist Sheet", {"sales_order": doc.name}):
            # parse out “First Last” from “ARTIST – First Last”
            parts = new_status.split(" - ", 1)[1].strip().split(" ", 1)
            first_name, last_name = parts[0], parts[1] if len(parts)>1 else ""

            # look up the Employee record
            emp = frappe.db.get_value("Employee",
                                    {"first_name": first_name, "last_name": last_name},
                                    "name")
            if emp:
                frappe.get_doc({
                    "doctype": "Artist Sheet",
                    "sales_order": doc.name,
                    "artist": emp,
                    "date_created": nowdate()
                }).insert(ignore_permissions=True)
            else:
                frappe.log_error(f"Artist Sheet: Employee not found for {first_name} {last_name}",
                                "Artist Sheet Creation")
