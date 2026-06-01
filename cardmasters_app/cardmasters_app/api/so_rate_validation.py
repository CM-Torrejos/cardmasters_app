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
        # 1. Fetch the designated bypass role from Cardmasters Settings
        bypass_role = frappe.db.get_single_value("Cardmasters Settings", "bypass_rate_validation_role")
        
        # 2. Get the current user's roles
        user_roles = frappe.get_roles(frappe.session.user)
        
        # 3. Check if the user has the bypass role
        has_bypass_role = bypass_role and (bypass_role in user_roles)
        
        if doc.docstatus == 0: # Draft / Save
            frappe.msgprint(
                msg=_("Sales order is saved but you cannot submit until price list rate issue is addressed"),
                title=_("Price Mismatch Warning"),
                indicator="orange"
            )
        elif doc.docstatus >= 1: # Submit or Update after Submit
            if has_bypass_role:
                frappe.msgprint(
                    msg=_("Rate and price list rate are not the same. This will affect accounting."),
                    title=_("Authorized Override"),
                    indicator="blue"
                )
            else:    
                frappe.throw(
                    _("Rate and price list rate are not the same. This will affect accounting, please forward this to a user with the '{0}' role.").format(bypass_role or "System Administrator")
                )