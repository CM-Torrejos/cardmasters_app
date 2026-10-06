frappe.ui.form.on("Cardmasters Settings", {
	setup(frm) {
		frm.set_query("default_bom_company", () => ({
			filters: { is_group: 0 },
		}));
	},
});
