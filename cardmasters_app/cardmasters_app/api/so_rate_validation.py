import frappe
from frappe import _
from frappe.utils import flt

def validate_item_rates(doc, method=None):
    """
    Validation: rate must match price_list_rate UNLESS price_list_rate is 0.
    """
    has_mismatch = False
    
    for item in doc.items:
        # Get the rates as floats
        rate = flt(item.rate)
        p_rate = flt(item.price_list_rate)
        
        # Check: If price list rate exists (is not 0) and doesn't match the rate
        if p_rate != 0 and rate != p_rate:
            has_mismatch = True
            break
            
    if has_mismatch:
        if doc.docstatus == 0: # Draft / Save
            frappe.msgprint(
                msg=_("Sales order is saved but you cannot submit until price list rate issue is addressed"),
                title=_("Price Mismatch Warning"),
                indicator="orange"
            )
        elif doc.docstatus >= 1: # Submit or Update after Submit
            frappe.throw(
                _("Rate and price list rate are not the same. This will affect accounting, please forward this to the system administrator.")
            )