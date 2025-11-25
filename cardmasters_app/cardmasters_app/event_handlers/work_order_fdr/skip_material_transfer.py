import frappe

@frappe.whitelist()
def get_user_role_profile_settings():
    profile_name = frappe.db.get_value("User", frappe.session.user, "role_profile_name")
    
    if not profile_name:
        return {"check_box": 0}

    should_check = frappe.db.get_value("Role Profile", profile_name, "custom_default_skip_transfer")
    
    return {"check_box": should_check or 0}