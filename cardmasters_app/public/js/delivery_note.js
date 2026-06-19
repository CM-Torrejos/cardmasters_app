frappe.ui.form.on('Delivery Note', {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && frm.doc.is_return) {
			frm.add_custom_button(__('Process Returned Item'), () => {
				process_returned_item(frm);
			});
		}
	}
});

function process_returned_item(frm) {
	const pending_rows = (frm.doc.items || []).filter(row => {
		const status = row.custom_return_processing_status || 'Pending';
		return status === 'Pending';
	});

	if (!pending_rows.length) {
		frappe.msgprint(__('There are no pending returned item rows to process.'));
		return;
	}

	if (pending_rows.length === 1) {
		show_return_processing_dialog(frm, pending_rows[0]);
		return;
	}

	const row_options = pending_rows.map(row => {
		return `${row.idx}. ${row.item_code} ${row.batch_no || ''} (${Math.abs(flt(row.qty))})`;
	});

	const selector = new frappe.ui.Dialog({
		title: __('Select Returned Item'),
		fields: [
			{
				fieldname: 'delivery_note_item',
				fieldtype: 'Select',
				label: __('Returned Item Row'),
				options: row_options.join('\n'),
				reqd: 1
			}
		],
		primary_action_label: __('Continue'),
		primary_action(values) {
			selector.hide();
			const selected_index = row_options.indexOf(values.delivery_note_item);
			const row = pending_rows[selected_index];
			show_return_processing_dialog(frm, row);
		}
	});

	selector.show();
}

function show_return_processing_dialog(frm, row) {
	const source_qty = Math.abs(flt(row.stock_qty || row.qty));
	const dialog = new frappe.ui.Dialog({
		title: __('Process Returned Item'),
		fields: [
			{fieldname: 'source_section', fieldtype: 'Section Break', label: __('Source')},
			{fieldname: 'item_code', fieldtype: 'Data', label: __('Item Code'), read_only: 1, default: row.item_code},
			{fieldname: 'item_name', fieldtype: 'Data', label: __('Item Name'), read_only: 1, default: row.item_name},
			{fieldname: 'batch_no', fieldtype: 'Data', label: __('Batch No'), read_only: 1, default: row.batch_no},
			{fieldname: 'column_break_source', fieldtype: 'Column Break'},
			{fieldname: 'qty', fieldtype: 'Float', label: __('Qty Returned'), read_only: 1, default: source_qty},
			{fieldname: 'warehouse', fieldtype: 'Link', options: 'Warehouse', label: __('Warehouse'), read_only: 1, default: row.warehouse},
			{fieldname: 'processing_section', fieldtype: 'Section Break'},
			{
				fieldname: 'outcome',
				fieldtype: 'Select',
				label: __('Outcome'),
				options: 'Convert to RM\nIssue as Damage',
				default: 'Convert to RM',
				reqd: 1,
				onchange: () => toggle_target_rows(dialog)
			},
			{
				fieldname: 'target_rows',
				fieldtype: 'Table',
				label: __('Target RM Rows'),
				cannot_add_rows: false,
				in_place_edit: true,
				fields: [
					{
						fieldname: 'item_code',
						fieldtype: 'Link',
						options: 'Item',
						label: __('RM Item'),
						in_list_view: 1,
						reqd: 1
					},
					{
						fieldname: 'qty',
						fieldtype: 'Float',
						label: __('Qty'),
						in_list_view: 1,
						reqd: 1,
						onchange: () => default_single_target_rate(frm, row, dialog)
					},
					{
						fieldname: 'basic_rate',
						fieldtype: 'Currency',
						label: __('Basic Rate'),
						in_list_view: 1,
						reqd: 1,
						onchange: () => update_target_amounts(dialog)
					},
					{
						fieldname: 'amount',
						fieldtype: 'Currency',
						label: __('Amount'),
						in_list_view: 1,
						read_only: 1
					}
				]
			},
			{
				fieldname: 'remarks',
				fieldtype: 'Small Text',
				label: __('Remarks')
			}
		],
		primary_action_label: __('Process'),
		primary_action(values) {
			update_target_amounts(dialog);
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.return_processing.process_returned_item',
				args: {
					delivery_note: frm.doc.name,
					delivery_note_item: row.name,
					outcome: values.outcome,
					target_rows: values.target_rows || [],
					remarks: values.remarks
				},
				freeze: true,
				freeze_message: __('Processing returned item...'),
				callback(response) {
					dialog.hide();
					if (response.message && response.message.stock_entry) {
						frappe.msgprint({
							title: __('Returned Item Processed'),
							message: __('Created Stock Entry {0}', [response.message.stock_entry]),
							indicator: 'green'
						});
					}
					frm.reload_doc();
				}
			});
		}
	});

	dialog.show();
	toggle_target_rows(dialog);
}

function toggle_target_rows(dialog) {
	const outcome = dialog.get_value('outcome');
	dialog.set_df_property('target_rows', 'hidden', outcome !== 'Convert to RM');
}

function default_single_target_rate(frm, row, dialog) {
	const target_rows = dialog.get_value('target_rows') || [];
	if (dialog.get_value('outcome') !== 'Convert to RM' || target_rows.length !== 1) {
		update_target_amounts(dialog);
		return;
	}

	const target = target_rows[0];
	if (!target.qty || target.basic_rate) {
		update_target_amounts(dialog);
		return;
	}

	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.return_processing.get_return_item_processing_defaults',
		args: {
			delivery_note: frm.doc.name,
			delivery_note_item: row.name,
			target_qty: target.qty
		},
		callback(response) {
			if (response.message) {
				target.basic_rate = response.message.default_basic_rate;
				target.amount = flt(target.qty) * flt(target.basic_rate);
				dialog.fields_dict.target_rows.grid.refresh();
			}
		}
	});
}

function update_target_amounts(dialog) {
	const target_rows = dialog.get_value('target_rows') || [];
	target_rows.forEach(row => {
		row.amount = flt(row.qty) * flt(row.basic_rate);
	});
	if (dialog.fields_dict.target_rows) {
		dialog.fields_dict.target_rows.grid.refresh();
	}
}
