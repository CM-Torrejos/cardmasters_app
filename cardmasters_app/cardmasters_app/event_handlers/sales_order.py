import frappe

# Customer must have an alias if its facebook
def validate_alias_on_facebook_channel(doc, method):
    has_alias = frappe.db.get_value("Sales Channel", doc.custom_sales_channel, "has_alias")
    print(has_alias)
    if has_alias == 1:
        print("For some reason im running? validate alias, and i have alias")
        customer = frappe.db.get_value("Customer", doc.customer, "custom_alias")
        if not customer:
            frappe.throw(("The selected Sales Channel requires you to input the Customer's alias in the Customer Masters"))

def check_artist_status(doc, method):
	so = frappe.get_doc("Sales Order", doc.sales_order)
	if so.custom_artist:
		so = apply_workflow(doc, "Begin Layout")
		so.save()
