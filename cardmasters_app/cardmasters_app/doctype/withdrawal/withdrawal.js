// Copyright (c) 2026, Shan Torrejos and contributors
// For license information, please see license.txt

function update_withdrawal_allocation(frm) {
	if (frm.doc.docstatus !== 0) return;
	const quantity_precision = frm.doc.__onload?.quantity_precision ??
		(cint(frappe.sys_defaults.float_precision) || 3);
	const scale = 10 ** quantity_precision;
	const units = (value) => Math.round(flt(value) * scale);
	const rows = frm.doc.work_orders || [];
	const quantities = rows.map((row) => Math.max(0, units(row.net_print_qty)));
	const total = quantities.reduce((sum, qty) => sum + qty, 0);
	const allowance = units(frm.doc.planned_withdrawal_qty) - total;
	// Integer arithmetic keeps proportional rounding identical to the server.
	const allocations = quantities.map((qty) => total > 0 && allowance >= 0 ?
		Number(BigInt(allowance) * BigInt(qty) / BigInt(total)) : 0);
	if (total > 0 && allowance >= 0) {
		let remaining = allowance - allocations.reduce((sum, qty) => sum + qty, 0);
		const order = quantities.map((qty, index) => ({
			index,
			remainder: BigInt(allowance) * BigInt(qty) % BigInt(total),
		})).sort((a, b) => a.remainder === b.remainder ? a.index - b.index :
			(a.remainder > b.remainder ? -1 : 1));
		for (const entry of order) {
			if (remaining <= 0) break;
			allocations[entry.index] += 1;
			remaining -= 1;
		}
	}
	frm.doc.net_print_qty = total / scale;
	frm.doc.allowance_qty = allowance / scale;
	rows.forEach((row, index) => {
		row.allowance_share_pct = total > 0 ? flt(quantities[index] / total * 100, 6) : 0;
		row.allocated_allowance_qty = allocations[index] / scale;
		row.withdrawal_qty = (quantities[index] + allocations[index]) / scale;
	});
	frm.refresh_field("net_print_qty");
	frm.refresh_field("allowance_qty");
	frm.refresh_field("work_orders");
}

frappe.ui.form.on("Withdrawal", {
	setup(frm) {
		frm.set_query("item", () => ({ filters: { is_stock_item: 1, disabled: 0 } }));
		for (const field of ["source_warehouse", "wip_warehouse"]) {
			frm.set_query(field, () => ({ filters: { company: frm.doc.company, is_group: 0, disabled: 0 } }));
		}
		frm.set_query("work_order", "work_orders", () => ({ filters: {
			company: frm.doc.company, docstatus: 1, status: ["not in", ["Closed", "Stopped", "Cancelled"]],
		} }));
	},
	onload(frm) {
		if (frm.is_new() && !frm.doc.company) {
			frm.set_value("company", frappe.defaults.get_user_default("Company"));
		}
	},
	refresh(frm) {
		update_withdrawal_allocation(frm);
		if (!frm.is_new() && frm.doc.docstatus !== 0) {
			frm.add_custom_button(__("Material Transfers"), () => {
				frappe.set_route("List", "Stock Entry", { custom_withdrawal: frm.doc.name });
			});
		}
	},
	planned_withdrawal_qty: update_withdrawal_allocation,
	validate: update_withdrawal_allocation,
});

frappe.ui.form.on("Withdrawal Work Order", {
	net_print_qty: update_withdrawal_allocation,
	work_orders_add: update_withdrawal_allocation,
	work_orders_remove: update_withdrawal_allocation,
});
