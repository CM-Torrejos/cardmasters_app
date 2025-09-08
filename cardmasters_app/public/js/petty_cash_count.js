frappe.ui.form.on('Petty Cash Count', {
	onload: function(frm){
		if (frm.doc.__islocal && !frm.doc.petty_cash_count_table.length) {
			const default_items = ['1000','500','200','100','50','20','10','5','1','0.25','0.05','0.10','0.01'];
			default_items.forEach(denom => {
				const row = frm.add_child('petty_cash_count_table');
				row.denomination = denom;
			});
			frm.refresh_field('petty_cash_count_table');
			recomputeTotals(frm);
		}
	},

	// keep this as an alias so server-side or UI changes that call it still work
	total_petty_cash_count: function(frm) {
		recomputeTotals(frm);
	},

	refresh: function(frm){
		if (!frm.is_new()){
			frm.add_custom_button(
				__('Sync Petty Cash Transactions'),
				() => syncPettyCashTransactions(frm)
			);

			if (frm.doc.workflow_state === "For Reimbursement") {
				frm.add_custom_button('Create Payment Entry', () => {
					frappe.model.with_doctype('Payment Entry', () => {
						const doc = frappe.model.get_new_doc('Payment Entry');
						frappe.model.set_value(doc.doctype, doc.name, 'payment_type', 'Pay');
						frappe.model.set_value(doc.doctype, doc.name, 'custom_receipt_type', 'Disbursement');
						frappe.model.set_value(doc.doctype, doc.name, 'mode_of_payment', 'Cheque');
						frappe.model.set_value(doc.doctype, doc.name, 'party_type', 'Supplier');
						frappe.set_route('Form', 'Payment Entry', doc.name);
					});
				});
			}
		}
	}
});

// petty cash count table: recompute when any relevant field changes
frappe.ui.form.on('Petty Cash Count Table', {
	denomination: calculate_row_amount,
	count: calculate_row_amount,
	count_iou: calculate_row_amount
});

// --- Helpers ---

function fltn(v){
	// robust float conversion for string/number/null
	return flt(v || 0);
}

// per-row amount calculation and totals refresh
function calculate_row_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const denom = fltn(row.denomination);
	const cnt   = fltn(row.count);
	const iou   = fltn(row.count_iou);

	// Keep row.amount as the WITH-IOU row total so existing UI keeps working
	row.amount = denom * (cnt + iou);

	frm.refresh_field('petty_cash_count_table');
	recomputeTotals(frm);
}

// recompute all totals (cash-only, IOU-only, and combined)
function recomputeTotals(frm){
	let total_cash_only = 0;
	let total_iou       = 0;
	let total_with_iou  = 0;

	(frm.doc.petty_cash_count_table || []).forEach(row => {
		const denom = fltn(row.denomination);
		const cnt   = fltn(row.count);
		const iou   = fltn(row.count_iou);

		total_cash_only += denom * cnt;
		total_iou       += denom * iou;
		// keep row.amount in sync if someone edited directly elsewhere
		row.amount       = denom * (cnt + iou);
	});

	total_with_iou = total_cash_only + total_iou;

	frm.set_value('total_petty_cash_count_no_iou', total_cash_only);
	frm.set_value('total_iou', total_iou);
	frm.set_value('total_petty_cash_count', total_with_iou);

	frm.refresh_field('petty_cash_count_table');
}

// --- Existing logic, with tiny log fix ---

async function syncPettyCashTransactions(frm) {
	try {
		await fetchLiquidatedTransactions(frm);
		await fetchUnliquidatedTransactions(frm);
		recomputeTotals(frm);           // ensure totals are fresh before balance
		updateCashCountBalance(frm);
	} catch (err){
		console.error('[Sync] Error:', err);
		frappe.msgprint({
			title: __('Sync Error'),
			message: err.message || 'An Unknown Error has Occured',
			indicator: 'red'
		});
	}
}

async function fetchUnliquidatedTransactions(frm) {
	console.log('[Unliq] Fetching…');
	frm.clear_table('unliquidated_transactions_table');

	const { message: transactions = [] } = await frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.petty_cash_count.get_unliquidated_transactions',
		args: { petty_cash_count: frm.doc.name },
	});

	let total = 0;
	transactions.forEach(tx => {
		const row = frm.add_child('unliquidated_transactions_table');
		row.material_request = tx.material_request;
		row.purchase_order = tx.purchase_order;
		row.amount_released = tx.amount_released;
		total += fltn(tx.amount_released);
	});

	frm.set_value('total_unliquidated', total);
	frm.refresh_field('unliquidated_transactions_table');
}

async function fetchLiquidatedTransactions(frm) {
	console.log('[Liq] Fetching…');
	frm.clear_table('liquidated_transactions_table');

	const { message: transactions = [] } = await frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.petty_cash_count.get_liquidated_transactions',
		args: { petty_cash_count: frm.doc.name },
	});

	let total = 0;

	transactions.forEach(tx => {
		const row = frm.add_child('liquidated_transactions_table');
		row.material_request   = tx.material_request;
		row.purchase_order     = tx.purchase_order;
		row.purchase_receipt   = tx.purchase_receipt;
		row.purchase_invoice   = tx.purchase_invoice;
		row.amount_paid        = fltn(tx.amount_paid);

		if (tx.outstanding_amount === 0) {
			row.reimbursed = 'Yes';
		} else if (tx.outstanding_amount === tx.amount_paid) {
			row.reimbursed = 'No';
		} else {
			row.reimbursed = 'Partially';
		}

		total += row.amount_paid;
	});

	frm.set_value('total_liquidated', total);
	frm.refresh_field('liquidated_transactions_table');

	console.log(`[Liq] Added ${transactions.length} rows. Total = ${total}`);
}

function updateCashCountBalance(frm) {
	const u = flt(frm.doc.total_unliquidated);
	const l = flt(frm.doc.total_liquidated);
	const f = flt(frm.doc.total_petty_cash_count); // WITH IOU
	const s = flt(frm.doc.allocated_revolving_fund);
	const balance = (u + l + f) - s;
	frm.set_value('balance', balance);
	console.log(`[Balance] (${u} + ${l} + ${f}) - ${s} = ${balance}`);
}
