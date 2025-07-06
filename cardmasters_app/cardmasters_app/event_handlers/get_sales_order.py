import frappe
@frappe.whitelist()
def get_sales_order_html(sales_order_name):
	print(f"[DEBUG] get_sales_order_html called with Sales Order: {sales_order_name}")
	if not sales_order_name:
		return "<div>No Sales Order Linked</div>"
	
	html = frappe.get_print(
		doctype="Sales Order",
		name=sales_order_name,
		print_format="SO - Standard Print",  # or your custom print format name
		as_pdf=False,
	)
	return html