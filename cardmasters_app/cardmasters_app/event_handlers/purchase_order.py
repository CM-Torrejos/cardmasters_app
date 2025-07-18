# my_custom_app/purchase_order.py

import frappe
from frappe import _

# TODO: fix logic for validating revolving fund
def validate_po_revolving(doc, method):
    """
    If *all* linked Material Requests on the PO items
    have custom_from_revolving_fund=True, then require
    doc.custom_from_revolving_fund to be True.
    """
    # only consider lines with a linked MR
    all_from_revolving = True
    for item in doc.items:
        if item.material_request:
            mr_flag = frappe.db.get_value(
                "Material Request",
                item.material_request,
                "custom_from_revolving_fund",
            )
            if not mr_flag:
                all_from_revolving = False
                break

    if all_from_revolving and not doc.custom_from_revolving_fund:
        frappe.throw(_(
            "All linked Material Requests are marked 'From Revolving Fund', "
            "so this Purchase Order must also be checked as such."
        ))
