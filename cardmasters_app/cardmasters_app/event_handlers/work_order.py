import frappe
from frappe.model.workflow import apply_workflow  # get_transitions no longer used

def inherit_remarks_particulars(doc, method=None):
    """Runs on Work Order (e.g., validate/before_save).
    Copies header + line-level fields from Sales Order when linked,
    but gracefully skips when there's no SO.
    """
    # --- No Sales Order? Skip politely and exit.
    if not doc.sales_order:
        frappe.msgprint("No Sales Order linked; skipping field inheritance.",
                        alert=True, indicator="orange")
        return

    # --- Sales Order name provided but missing in DB
    if not frappe.db.exists("Sales Order", doc.sales_order):
        frappe.msgprint(f"Sales Order {doc.sales_order} not found; skipping field inheritance.",
                        alert=True, indicator="orange")
        return

    # --- Load Sales Order and copy header fields
    so = frappe.get_doc("Sales Order", doc.sales_order)
    doc.custom_customer = so.get("customer")
    doc.custom_remarks  = so.get("custom_remarks")
    doc.custom_for_new_flow = so.get("custom_for_new_flow")
    doc.custom_deadline = so.get("delivery_date")
    doc.custom_remarks_production = so.get("custom_remarks_production")
    doc.custom_rush_order = so.get("custom_rush_order")

    # --- Artist Card tied to this SO (optional)
    artist_card = frappe.db.get_value("Artist Card", {"sales_order": doc.sales_order}, "name")
    if artist_card:
        doc.custom_artist_card = artist_card
        ac = frappe.get_doc("Artist Card", artist_card)
        doc.custom_artist_bom = ac.get("bom")
        doc.custom_artist_remarks = ac.get("remarks")
        doc.custom_artist_assigned = ac.get("artist")
    else:
        frappe.msgprint("This Work Order has no Artist Card. Be warned!",
                        alert=True, indicator="orange")

    # === Restore the per-item inheritance (safe)
    so_item_row = None

    if getattr(doc, "sales_order_item", None):
        try:
            so_item_row = frappe.get_doc("Sales Order Item", doc.sales_order_item)
        except frappe.DoesNotExistError:
            for row in so.items:
                if row.name == doc.sales_order_item:
                    so_item_row = row
                    break

    if not so_item_row and doc.production_item:
        for row in so.items:
            if row.item_code == doc.production_item:
                so_item_row = row
                break

    if so_item_row:
        doc.custom_item_specifics = so_item_row.get("custom_item_specifics")
        doc.custom_particulars    = so_item_row.get("custom_particulars")
        
        target_code = getattr(so_item_row, "item_code", None) or doc.production_item
        if target_code and getattr(doc, "required_items", None):
            for req in doc.required_items:
                if req.item_code == target_code:
                    req.custom_item_specifics = doc.custom_item_specifics
                    break
    else:
        hint = (f"SO Item not matched. Checked sales_order_item={getattr(doc, 'sales_order_item', None)} "
                f"and production_item={getattr(doc, 'production_item', None)}.")
        frappe.msgprint(f"Could not copy item-level specifics/particulars. {hint}",
                        alert=True, indicator="orange")


def before_work_order_submit(doc, method):
    """On WO submit, advance the SO workflow from 'Artist' → 'Begin Production' when linked."""
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
            frappe.log_error(frappe.get_traceback(),
                             f"Failed to advance Sales Order workflow for {so.name}")
            frappe.msgprint("Could not advance Sales Order workflow. Check state/permissions.",
                            alert=True, indicator="red")


def clear_child_rows(doc, method):
    # Clean up child table rows for this Work Order as needed.
    frappe.db.delete("Artist BOM table", {"parent": doc.name})
