import frappe
@frappe.whitelist()
def get_sales_order_html(sales_order_name):
	if not sales_order_name:
		return "<div>No Sales Order Linked</div>"
	
	try:
		print_format = get_default_print_format("Sales Order")

		html = frappe.get_print(
			doctype="Sales Order",
			name=sales_order_name,
			print_format=print_format,
			as_pdf=False,
		)
		return html
	except Exception as e:
		frappe.log_error(f"Error generating Sales Order HTML: {e}")
		return "<div>Error loading Sales Order</div>"

def get_default_print_format(doctype):
	meta = frappe.get_meta(doctype)

	if meta.default_print_format:
		return meta.default_print_format
	
	return meta.default_print_format or "Standard"