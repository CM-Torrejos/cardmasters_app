frappe.ui.form.on("Purchase Receipt", {
	refresh(frm) {
		if (frm.doc.docstatus === 0 && !frm.doc.is_return) {
			frm.add_custom_button(
				__("Sales Order"),
				function () {
					if (!frm.doc.supplier) {
						frappe.throw({
							title: __("Mandatory"),
							message: __("Please Select a Supplier"),
						});
					}

					erpnext.utils.map_current_doc({
						method: "cardmasters_app.cardmasters_app.api.purchase_receipt.make_purchase_receipt_from_sales_order",
						source_doctype: "Sales Order",
						target: frm,
						setters: {
							customer: undefined,
							delivery_date: undefined,
						},
						get_query_filters: {
							docstatus: 1,
							status: ["not in", ["Closed", "On Hold", "Completed"]],
							company: frm.doc.company,
						},
						allow_child_item_selection: true,
						child_fieldname: "items",
						child_columns: ["item_code", "item_name", "qty", "delivered_qty"],
					});
				},
				__("Get Items From")
			);
		}
	},
});