frappe.ui.form.on('Delivery Note', {
	setup(frm) {
		frm.set_query('custom_damages_and_returns', () => {
			return {
				filters: {
					type: 'Return'
				}
			};
		});

		frm.set_query('custom_return_warehouse', () => {
			return {
				filters: {
					company: frm.doc.company,
					is_group: 0,
					disabled: 0,
					custom_accepts_returns: 1
				}
			};
		});
	},

	refresh(frm) {
		toggle_damages_and_returns_requirement(frm);

		if (frm.doc.is_return && frm.doc.docstatus !== 1) {
			frm.remove_custom_button(__('Credit Note'), __('Create'));
			frm.remove_custom_button(__('Work Order'), __('Create'));
			frm.page.get_inner_group_button(__('Create')).hide();
		}

		if (frm.doc.docstatus === 1 && frm.doc.is_return) {
			frm.add_custom_button(__('Work Order'), () => {
				make_work_order_from_sales_return(frm);
			}, __('Create'));

			frm.add_custom_button(__('Deliver'), () => {
				make_delivery_note_from_sales_return(frm);
			}, __('Actions'));

			frm.add_custom_button(__('Process Returned Item'), () => {
				process_returned_item(frm);
			});
		}
	},

	is_return(frm) {
		toggle_damages_and_returns_requirement(frm);
	}
});

async function make_work_order_from_sales_return(frm) {
	const returned_rows = get_sales_return_delivery_rows(frm).filter(row => {
		return row.against_sales_order && row.so_detail;
	});

	if (!returned_rows.length) {
		frappe.msgprint(__('Could not find any returned item rows linked to a Sales Order.'));
		return;
	}

	if (returned_rows.length === 1) {
		await open_work_order_from_return_row(frm, returned_rows[0]);
		return;
	}

	const row_options = returned_rows.map(row => {
		return `${row.idx}. ${row.item_code} ${row.batch_no || ''} (${Math.abs(flt(row.qty))})`;
	});

	const dialog = new frappe.ui.Dialog({
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
		primary_action_label: __('Create Work Order'),
		async primary_action(values) {
			dialog.hide();
			const selected_index = row_options.indexOf(values.delivery_note_item);
			await open_work_order_from_return_row(frm, returned_rows[selected_index]);
		}
	});

	dialog.show();
}

async function open_work_order_from_return_row(frm, row) {
	await with_doctype('Work Order');

	const so_item = await get_sales_order_item_details(row.so_detail);
	const work_order = frappe.model.get_new_doc('Work Order');
	const qty = Math.abs(flt(row.qty));

	set_work_order_value(work_order, 'company', frm.doc.company);
	set_work_order_value(work_order, 'production_item', row.item_code);
	set_work_order_value(work_order, 'item_name', row.item_name);
	set_work_order_value(work_order, 'qty', qty);
	set_work_order_value(work_order, 'stock_uom', row.stock_uom);
	set_work_order_value(work_order, 'custom_production_type', 'Backjob');
	set_work_order_value(work_order, 'custom_sales_return_reference', frm.doc.name);
	set_work_order_value(work_order, 'custom_document', 'Sales Order');
	set_work_order_value(work_order, 'custom_document_id', row.against_sales_order);
	set_work_order_value(work_order, 'custom_document_item_id', row.so_detail);
	set_work_order_value(work_order, 'custom_customer', frm.doc.customer);
	set_work_order_value(work_order, 'custom_for_branch', frm.doc.branch);
	set_work_order_value(work_order, 'custom_item_specifics', row.custom_item_specifics || so_item.custom_item_specifics);
	set_work_order_value(work_order, 'custom_particulars', get_backjob_particulars(row.custom_particulars || so_item.custom_particulars));
	set_work_order_value(work_order, 'description', row.description);

	if (so_item.bom_no) {
		set_work_order_value(work_order, 'bom_no', so_item.bom_no);
	}

	frappe.set_route('Form', 'Work Order', work_order.name);
}

function get_backjob_particulars(particulars) {
	const clean_particulars = (particulars || '').trim();
	if (!clean_particulars) {
		return 'BACKJOB -';
	}

	if (clean_particulars.toUpperCase().startsWith('BACKJOB - ')) {
		return clean_particulars;
	}

	return `BACKJOB - ${clean_particulars}`;
}

async function get_sales_order_item_details(so_detail) {
	if (!so_detail) {
		return {};
	}

	const response = await frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.work_order.get_sales_order_item_work_order_defaults',
		args: {
			so_detail
		}
	});

	return response.message || {};
}

function set_work_order_value(work_order, fieldname, value) {
	if (value === undefined || value === null || value === '') {
		return;
	}

	if (frappe.meta.has_field('Work Order', fieldname)) {
		work_order[fieldname] = value;
	}
}

async function make_delivery_note_from_sales_return(frm) {
	const returned_rows = get_sales_return_delivery_rows(frm);

	if (!returned_rows.length) {
		frappe.msgprint(__('Could not find any returned item rows to deliver.'));
		return;
	}

	await with_doctype('Delivery Note');

	const delivery_note = frappe.model.get_new_doc('Delivery Note');
	delivery_note.company = frm.doc.company;
	delivery_note.custom_batched = frm.doc.custom_batched || 1;
	delivery_note.custom_repack_reference = frm.doc.custom_repack_reference;

	returned_rows.forEach(returned_row => {
		const delivery_note_item = frappe.model.add_child(
			delivery_note,
			'Delivery Note Item',
			'items'
		);
		const qty = Math.abs(flt(returned_row.qty));
		const stock_qty = Math.abs(flt(returned_row.stock_qty || returned_row.qty));

		delivery_note_item.item_code = returned_row.item_code;
		delivery_note_item.item_name = returned_row.item_name;
		delivery_note_item.description = returned_row.description;
		delivery_note_item.qty = qty;
		delivery_note_item.stock_qty = stock_qty;
		delivery_note_item.uom = returned_row.uom;
		delivery_note_item.stock_uom = returned_row.stock_uom;
		delivery_note_item.conversion_factor = returned_row.conversion_factor || 1;
		delivery_note_item.warehouse = returned_row.warehouse;
		delivery_note_item.batch_no = returned_row.batch_no;
		delivery_note_item.use_serial_batch_fields = 1;
		delivery_note_item.custom_item_specifics = returned_row.custom_item_specifics;
	});

	frappe.set_route('Form', 'Delivery Note', delivery_note.name);
}

function get_sales_return_delivery_rows(frm) {
	return (frm.doc.items || []).filter(row => row.item_code && row.warehouse);
}

function with_doctype(doctype) {
	return new Promise(resolve => {
		frappe.model.with_doctype(doctype, resolve);
	});
}

function toggle_damages_and_returns_requirement(frm) {
	if (!frm.fields_dict.custom_damages_and_returns) {
		return;
	}

	frm.toggle_reqd('custom_damages_and_returns', Boolean(cint(frm.doc.is_return)));
	frm.toggle_display('custom_damages_and_returns', Boolean(cint(frm.doc.is_return)));

	if (frm.fields_dict.custom_return_warehouse) {
		frm.toggle_reqd('custom_return_warehouse', Boolean(cint(frm.doc.is_return)));
		frm.toggle_display('custom_return_warehouse', Boolean(cint(frm.doc.is_return)));
	}
}

function prompt_for_damages_and_returns(frm) {
	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.return_processing.get_sales_return_destination_defaults',
		args: {
			company: frm.doc.company
		},
		callback(response) {
			show_sales_return_dialog(frm, response.message || {});
		}
	});
}

function show_sales_return_dialog(frm, defaults) {
	const dialog = new frappe.ui.Dialog({
		title: __('Create Sales Return'),
		fields: [
			{
				fieldname: 'custom_damages_and_returns',
				fieldtype: 'Link',
				label: __('Damages and Returns'),
				options: 'Damages and Returns',
				reqd: 1,
				get_query: () => {
					return {
						filters: {
							type: 'Return'
						}
					};
				}
			},
			{
				fieldname: 'return_warehouse',
				fieldtype: 'Link',
				label: __('Returned Item Destination Warehouse'),
				options: 'Warehouse',
				reqd: 1,
				default: defaults.return_warehouse,
				description: __('Only warehouses marked as accepting returns are allowed.'),
				get_query: () => {
					return {
						filters: {
							company: frm.doc.company,
							is_group: 0,
							disabled: 0,
							custom_accepts_returns: 1
						}
					};
				}
			}
		],
		primary_action_label: __('Create Sales Return'),
		primary_action(values) {
			dialog.hide();
			frappe.model.open_mapped_doc({
				method: 'cardmasters_app.cardmasters_app.api.return_processing.make_sales_return_with_damages_and_returns',
				frm,
				run_link_triggers: true,
				args: {
					damages_and_returns: values.custom_damages_and_returns,
					return_warehouse: values.return_warehouse
				}
			});
		}
	});

	dialog.show();
}

if (window.erpnext && erpnext.stock && erpnext.stock.DeliveryNoteController) {
	erpnext.stock.DeliveryNoteController.prototype.make_sales_return = function() {
		prompt_for_damages_and_returns(this.frm);
	};
}

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
			{fieldname: 'rm_section', fieldtype: 'Section Break', label: __('RM Conversion')},
			{
				fieldname: 'rm_rows',
				fieldtype: 'Table',
				label: __('RM Conversion Rows'),
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
						onchange: () => default_single_target_rate(frm, row, dialog, true)
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
			{fieldname: 'damage_section', fieldtype: 'Section Break', label: __('Damage Issuance')},
			{
				fieldname: 'damage_rows',
				fieldtype: 'Table',
				label: __('Damage Issuance Rows'),
				cannot_add_rows: false,
				in_place_edit: true,
				fields: [
					{
						fieldname: 'item_code',
						fieldtype: 'Data',
						label: __('Item Code'),
						default: row.item_code,
						read_only: 1,
						in_list_view: 1
					},
					{
						fieldname: 'batch_no',
						fieldtype: 'Data',
						label: __('Batch No'),
						default: row.batch_no,
						read_only: 1,
						in_list_view: 1
					},
					{
						fieldname: 'qty',
						fieldtype: 'Float',
						label: __('Qty'),
						in_list_view: 1,
						reqd: 1,
						onchange: () => default_single_target_rate(frm, row, dialog, true)
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
			if (!validate_processing_quantities(dialog, source_qty)) {
				return;
			}
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.return_processing.process_returned_item',
				args: {
					delivery_note: frm.doc.name,
					delivery_note_item: row.name,
					rm_rows: values.rm_rows || [],
					damage_rows: values.damage_rows || [],
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
}

function default_single_target_rate(frm, row, dialog, force = false) {
	const target_rows = dialog.get_value('rm_rows') || [];
	if (target_rows.length !== 1) {
		update_target_amounts(dialog);
		return;
	}

	const target = target_rows[0];
	if (!target.qty || (target.basic_rate && !force)) {
		update_target_amounts(dialog);
		return;
	}

	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.return_processing.get_return_item_processing_defaults',
		args: {
			delivery_note: frm.doc.name,
			delivery_note_item: row.name,
			target_qty: target.qty,
			damage_qty: get_damage_qty(dialog)
		},
		callback(response) {
			if (response.message) {
				target.basic_rate = response.message.default_basic_rate;
				target.amount = flt(target.qty) * flt(target.basic_rate);
				dialog.fields_dict.rm_rows.grid.refresh();
			}
		}
	});
}

function update_target_amounts(dialog) {
	const target_rows = dialog.get_value('rm_rows') || [];
	target_rows.forEach(row => {
		row.amount = flt(row.qty) * flt(row.basic_rate);
	});
	if (dialog.fields_dict.rm_rows) {
		dialog.fields_dict.rm_rows.grid.refresh();
	}
}

function get_damage_qty(dialog) {
	return (dialog.get_value('damage_rows') || []).reduce((total, row) => total + flt(row.qty), 0);
}

function validate_processing_quantities(dialog, source_qty) {
	const rm_rows = dialog.get_value('rm_rows') || [];
	const damage_rows = dialog.get_value('damage_rows') || [];
	const damage_qty = get_damage_qty(dialog);

	if (!rm_rows.length && !damage_rows.length) {
		frappe.msgprint(__('Add at least one RM conversion row or damage issuance row.'));
		return false;
	}
	if (damage_qty > source_qty) {
		frappe.msgprint(__('Damage quantity cannot exceed the returned quantity.'));
		return false;
	}
	if (!rm_rows.length && Math.abs(damage_qty - source_qty) > 0.000001) {
		frappe.msgprint(__('When there are no RM conversion rows, the full returned quantity must be issued as damage.'));
		return false;
	}
	if (rm_rows.length && damage_qty >= source_qty) {
		frappe.msgprint(__('RM conversion requires some of the returned quantity to remain after damage issuance.'));
		return false;
	}
	return true;
}
