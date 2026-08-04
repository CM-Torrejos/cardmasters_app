frappe.ui.form.on("Customer", {
	refresh(frm) {
		frm.toggle_display(
			["custom_partly_paid_sales_orders", "custom_fully_unpaid_sales_orders"],
			false
		);

		if (frm.is_new()) {
			return;
		}

		frappe.call({
			method: "cardmasters_app.cardmasters_app.api.customer_dashboard.get_sales_order_payment_counts",
			args: { customer: frm.doc.name },
			callback({ message }) {
				if (!message) return;

				add_payment_indicator(frm, "custom_partly_paid_sales_orders", message.partly_paid, {
					customer: frm.doc.name,
					docstatus: 1,
					custom_outstanding_balance: [">", 0],
				});
				add_payment_indicator(frm, "custom_fully_unpaid_sales_orders", message.fully_unpaid, {
					customer: frm.doc.name,
					docstatus: 1,
					custom_outstanding_balance: [">", 0],
				});
			},
		});
	},
});

function add_payment_indicator(frm, fieldname, count, filters) {
	const field = frm.get_field(fieldname);
	if (!field) return;

	const value = Number(count) || 0;
	const css_class = `customer-payment-stat-${fieldname}`;
	frm.dashboard.stats_area_row.find(`.${css_class}`).remove();

	const indicator = frm.dashboard
		.add_indicator(`${__(field.df.label)}: <strong>${value}</strong>`, "blue")
		.addClass(css_class)
		.attr({ role: "link", tabindex: 0 })
		.css("cursor", "pointer")
		.on("click", (event) => {
			event.preventDefault();
			frappe.route_options = filters;
			frappe.set_route("List", "Sales Order");
		})
		.on("keydown", (event) => {
			if (event.key === "Enter" || event.key === " ") {
				event.preventDefault();
				indicator.trigger("click");
			}
		});
}
