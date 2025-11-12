import frappe

@frappe.whitelist()
def switch_theme(theme):
	frappe.logger().error(f"[CUSTOM SWITCH THEME] Called with theme={theme}")
	if theme in ["Dark", "Light", "Automatic", "Newdark"]:
		frappe.db.set_value("User", frappe.session.user, "desk_theme", theme)
