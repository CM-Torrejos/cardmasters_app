// Copyright (c) 2026, Shan Torrejos and contributors
// For license information, please see license.txt

function update_withdrawal_allocation(frm) {
	if (frm.doc.docstatus !== 0) return;
	const scale = 1000000;
	const units = (value) => Math.round(flt(value) * scale);
	const rows = frm.doc.work_orders || [];
	const quantities = rows.map((row) => Math.max(0, units(row.net_print_qty)));
	const total = quantities.reduce((sum, qty) => sum + qty, 0);
	const allowance = units(frm.doc.planned_withdrawal_qty) - total;
	const allocations = quantities.map((qty) =>
		total > 0 && allowance >= 0 ? Math.floor((allowance * qty) / total) : 0
	);
	if (total > 0 && allowance >= 0) {
		let remaining = allowance - allocations.reduce((sum, qty) => sum + qty, 0);
		const order = quantities.map((qty, index) => ({
			index,
			remainder: (allowance * qty) / total - allocations[index],
		})).sort((a, b) => b.remainder - a.remainder || a.index - b.index);
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
	refresh: update_withdrawal_allocation,
	planned_withdrawal_qty: update_withdrawal_allocation,
	validate: update_withdrawal_allocation,
});

frappe.ui.form.on("Withdrawal Work Order", {
	net_print_qty: update_withdrawal_allocation,
	work_orders_add: update_withdrawal_allocation,
	work_orders_remove: update_withdrawal_allocation,
});
