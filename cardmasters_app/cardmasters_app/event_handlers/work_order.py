import frappe
from frappe.model.workflow import apply_workflow  # get_transitions not used; you can remove it

def inherit_remarks_particulars(doc, method=None):
    # No Sales Order linked? Skip quietly with a friendly alert.
    if not doc.sales_order:
        frappe.msgprint("No Sales Order linked; skipping field inheritance.",
                        alert=True, indicator="orange")
        return

    so_name = doc.sales_order

    # SO name given but not found in DB → skip safely.
    if not frappe.db.exists("Sales Order", so_name):
        frappe.msgprint(f"Sales Order {so_name} not found; skipping field inheritance.",
                        alert=True, indicator="orange")
        return

    # Load SO and inherit header fields
    so = frappe.get_doc("Sales Order", so_name)
    doc.custom_remarks  = so.get("custom_remarks")
    doc.custom_deadline = so.get("delivery_date")

    # Artist Card tied to this Sales Order (if any)
    artist_card = frappe.db.get_value("Artist Card", {"sales_order": so_name}, "name")
    if artist_card:
        doc.custom_artist_card    = artist_card
        ac = frappe.get_doc("Artist Card", artist_card)
        doc.custom_artist_bom     = ac.get("bom")
        doc.custom_artist_remarks = ac.get("remarks")
    else:
        frappe.msgprint("This work order has no artist card. Be Warned!",
                        alert=True, indicator="orange")


def before_work_order_submit(doc, method):
    # No Sales Order linked? Nothing to transition.
    if not doc.sales_order:
        return

    so_name = doc.sales_order

    if not frappe.db.exists("Sales Order", so_name):
        frappe.msgprint(f"Sales Order {so_name} not found; skipping workflow transition.",
                        alert=True, indicator="orange")
        return

    so = frappe.get_doc("Sales Order", so_name)

    if so.workflow_state == "Artist":
        try:
            apply_workflow(so, "Begin Production")
            so.save()
        except Exception:
            # Don’t block Work Order submit — just log and notify.
            frappe.log_error(frappe.get_traceback(),
                             f"Failed to advance Sales Order workflow for {so.name}")
            frappe.msgprint("Could not advance Sales Order workflow. Check state/permissions.",
                            alert=True, indicator="red")


def clear_child_rows(doc, method):
    # 'My Child Table' = your child‐DocType
    frappe.db.delete("Artist BOM table", {"parent": doc.name})
