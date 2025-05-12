import frappe

def inherit_remarks_particulars(doc, method=None):
    print("im running")
    if not doc.sales_order:
        return

    # load SO
    so = frappe.get_doc("Sales Order", doc.sales_order)

    # inherit header fields
    doc.custom_remarks = so.get("custom_remarks")
    doc.custom_deadline = so.get("delivery_date")

    # fetch the Sales Order Item row matching production_item
    so_item_row = None
    if doc.production_item:
        for row in so.items:
            if row.item_code == doc.production_item:
                so_item_row = row
                break

    if so_item_row:
        # inherit line-level fields
        doc.custom_item_specifics = so_item_row.get("custom_item_specifics")
        doc.custom_particulars      = so_item_row.get("custom_particulars")

        # now update the matching required_item on the Work Order
        for req in doc.required_items:
            if req.item_code == doc.production_item:
                # set the specifics on the raw material line
                req.custom_item_specifics = doc.custom_item_specifics
                break
