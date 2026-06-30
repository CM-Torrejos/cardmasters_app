frappe.ui.form.on("Cardmasters Company Settings", {
	setup(frm) {
		frm.set_query("company", () => ({
			filters: { is_group: 0 },
		}));

		frm.set_query("income_account", "item_group_account_mappings", () => ({
			filters: {
				company: frm.doc.company,
				root_type: "Income",
				is_group: 0,
				disabled: 0,
			},
		}));

		for (const fieldname of ["buying_cost_center", "selling_cost_center"]) {
			frm.set_query(fieldname, "item_group_account_mappings", () => ({
				filters: {
					company: frm.doc.company,
					is_group: 0,
					disabled: 0,
				},
			}));
		}

		frm.set_query("default_warehouse", "item_group_account_mappings", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
			},
		}));

		for (const fieldname of ["return_warehouse", "dnr_holding_warehouse", "master_warehouse", "damage_warehouse"]) {
			frm.set_query(fieldname, () => ({
				filters: {
					company: frm.doc.company,
					is_group: 0,
					disabled: 0,
				},
			}));
		}

		frm.set_query("default_bom_component", () => ({
			filters: {
				disabled: 0,
				is_stock_item: 1,
			},
		}));

		frm.set_query("default_bom_source_warehouse", () => ({
			filters: {
				company: frm.doc.company,
				is_group: 0,
				disabled: 0,
			},
		}));
	},
});
