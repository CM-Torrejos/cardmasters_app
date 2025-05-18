import frappe
from frappe.utils import nowdate


def before_save(doc, method):
    new_status = doc.progress_status or ""
    # Only care when moving into one of the ARTIST statuses
    if new_status.startswith("ARTIST"):
        # fetch the *old* status from the DB
        old_status = frappe.db.get_value("Sales Order", doc.name, "progress_status")

        # 1) Delete previous sheets if we were *not* coming from PRODUCTION
        if old_status != "PRODUCTION":
            for sheet_name in frappe.get_all(
                "Artist Sheet",
                filters={"sales_order": doc.name},
                pluck="name"
            ):
                frappe.delete_doc("Artist Sheet", sheet_name, force=True)

        # 2) If no sheet exists now, auto-create one
        exists = frappe.db.exists("Artist Sheet", {"sales_order": doc.name})
        if not exists:
            # parse out "First Last" from "ARTIST - First Last"
            try:
                _, full_name = new_status.split(" - ", 1)
                first_name, last_name = full_name.split(" ", 1)
            except ValueError:
                frappe.msgprint(f"Could not parse artist name from '{new_status}'")
                return

            # look up the Employee by first & last name
            emp = frappe.db.get_value(
                "Employee",
                {"first_name": first_name, "last_name": last_name},
                "name"
            )

            if not emp:
                frappe.msgprint(f"No Employee found for {first_name} {last_name}")
                return

            # build and insert the Artist Sheet
            sheet = frappe.new_doc("Artist Sheet")
            sheet.sales_order = doc.name
            sheet.artist     = emp
            sheet.date_created = nowdate()
            sheet.insert(ignore_permissions=True)

            