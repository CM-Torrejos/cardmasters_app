frappe.ui.form.on('Material Request', {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !['Stopped', 'Cancelled'].includes(frm.doc.status)
			&& frappe.model.can_write('Material Request')) {
			frm.add_custom_button(__('Update Details'), () => show_material_request_update_details(frm));
		}

		if (
			!frm.is_new() &&
			frm.doc.docstatus === 1 &&
			frm.doc.status !== 'Stopped' &&
			frappe.model.can_create('Stock Entry')
		) {
			add_material_request_batch_stock_entry_button(frm);
		}

		if (
			!frm.is_new() &&
			frm.doc.docstatus === 1 &&
			frappe.model.can_create('Artist Card')
		) {
			add_material_request_artist_card_button(frm);
		}

		if (
			frm.doc.docstatus !== 1 ||
			frm.doc.material_request_type !== 'Manufacture' ||
			!frappe.model.can_create('Work Order')
		) {
			return;
		}

		setTimeout(() => {
			frm.page.remove_inner_button(__('Work Order'), __('Create'));
			add_material_request_work_order_button(frm);
		}, 100);
	}
});

function show_material_request_update_details(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__('Save your changes before updating details.'));
		return;
	}
	const meta = frappe.get_meta('Material Request Item');
	const precision = fieldname => meta.fields.find(field => field.fieldname === fieldname)?.precision;
	const editable_fields = ['qty', 'rate', 'uom', 'conversion_factor', 'schedule_date', 'warehouse', 'from_warehouse',
		'custom_item_specifics', 'custom_particulars'];
	const data = (frm.doc.items || []).map(row => ({
		docname: row.name,
		item_code: row.item_code,
		...Object.fromEntries(editable_fields.map(field => [field, row[field]]))
	}));
	const modified = frm.doc.modified;
	let saving = false;
	let pending_item_lookups = 0;
	const dialog = new frappe.ui.Dialog({
		title: __('Update Details'),
		size: 'extra-large',
		fields: [{
			fieldname: 'items', fieldtype: 'Table', label: __('Items'), reqd: 1,
			cannot_add_rows: !frappe.model.can_create('Material Request'), cannot_delete_rows: false,
			in_place_edit: false, data,
			fields: [
				{ fieldname: 'docname', fieldtype: 'Data', hidden: 1, read_only: 1 },
				{
					fieldname: 'item_code', fieldtype: 'Link', options: 'Item', label: __('Item Code'),
					reqd: 1, read_only_depends_on: 'eval:!!doc.docname', in_list_view: 1,
					get_query: () => ({ query: 'erpnext.controllers.queries.item_query' }),
					async onchange() {
						const row = this.doc;
						const item_code = this.value;
						if (row.docname || !item_code) return;
						pending_item_lookups++;
						row.uom = '';
						row.conversion_factor = 0;
						try {
							const response = await frappe.call({
								method: 'erpnext.stock.get_item_details.get_item_details',
								args: { doc: frm.doc, args: {
									doctype: 'Material Request', name: frm.doc.name, item_code,
									company: frm.doc.company, material_request_type: frm.doc.material_request_type,
									transaction_date: frm.doc.transaction_date, qty: row.qty || 1,
									set_warehouse: frm.doc.set_warehouse, buying_price_list: frm.doc.buying_price_list
								} }
							});
							if (row.item_code === item_code && response.message) {
								const defaults = response.message;
								Object.assign(row, {
									uom: defaults.uom || defaults.stock_uom,
									conversion_factor: defaults.conversion_factor || 1,
									rate: defaults.rate ?? defaults.price_list_rate ?? 0,
									warehouse: frm.doc.set_warehouse || defaults.warehouse,
									from_warehouse: frm.doc.set_from_warehouse,
									schedule_date: row.schedule_date || frm.doc.schedule_date || defaults.schedule_date
								});
								dialog.fields_dict.items.grid.refresh();
							}
						} finally {
							pending_item_lookups--;
						}
					}
				},
				{ fieldname: 'schedule_date', fieldtype: 'Date', label: __('Required By'), default: frm.doc.schedule_date, reqd: 1, in_list_view: 1 },
				{ fieldname: 'qty', fieldtype: 'Float', label: __('Qty'), default: 1, reqd: 1, in_list_view: 1, precision: precision('qty') },
				{ fieldname: 'rate', fieldtype: 'Currency', label: __('Rate'), in_list_view: 1, precision: precision('rate') },
				{
					fieldname: 'uom', fieldtype: 'Link', options: 'UOM', label: __('UOM'), reqd: 1,
					async onchange() {
						const row = this.doc;
						const uom = this.value;
						if (!uom) return;
						row.conversion_factor = 0;
						pending_item_lookups++;
						try {
							const response = await frappe.call({
								method: 'erpnext.stock.get_item_details.get_conversion_factor',
								args: { item_code: row.item_code, uom }
							});
							if (row.uom === uom) {
								row.conversion_factor = response.message?.conversion_factor || 0;
								dialog.fields_dict.items.grid.refresh();
							}
						} finally {
							pending_item_lookups--;
						}
					}
				},
				{ fieldname: 'conversion_factor', fieldtype: 'Float', label: __('Conversion Factor'), reqd: 1, precision: precision('conversion_factor') },
				...['warehouse', 'from_warehouse'].map(fieldname => ({
					fieldname, fieldtype: 'Link', options: 'Warehouse',
					label: fieldname === 'warehouse' ? __('Target Warehouse') : __('Source Warehouse'),
					read_only_depends_on: 'eval:!!doc.docname',
					get_query: () => ({ filters: { company: frm.doc.company, is_group: 0 } })
				})),
				{ fieldname: 'custom_item_specifics', fieldtype: 'Small Text', label: __('Item Specifics'), in_list_view: 1 },
				{ fieldname: 'custom_particulars', fieldtype: 'Text', label: __('Particulars'), in_list_view: 1 }
			]
		}],
		primary_action_label: __('Update'),
		primary_action(values) {
			if (!values || saving) return;
			if (pending_item_lookups) {
				frappe.msgprint(__('Please wait for item details and UOM conversion factors to load.'));
				return;
			}
			const items = values.items.map(row => ({
				...row,
				custom_item_specifics: String(row.custom_item_specifics || '').trim(),
				custom_particulars: String(row.custom_particulars || '').trim()
			}));
			update(items);
		}
	});
	async function update(items, confirmed = false) {
		if (saving) return;
		saving = true;
		dialog.disable_primary_action();
		try {
			const response = await frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.material_request.update_details',
				args: { material_request: frm.doc.name, items, modified, confirm_work_orders: confirmed },
				freeze: true, freeze_message: __('Updating Material Request details...')
			});
			if (response.exc) return;
			if (response.message?.confirmation_required) {
				frappe.confirm(response.message.message, () => update(items, true));
				return;
			}
			dialog.hide();
			await frm.reload_doc();
			frappe.show_alert({ message: __('Material Request details updated.'), indicator: 'green' });
		} finally {
			saving = false;
			dialog.enable_primary_action();
		}
	}
	dialog.show();
}

function add_material_request_batch_stock_entry_button(frm) {
	frm.add_custom_button(__('Batch Stock Entry'), () => {
		frappe.model.open_mapped_doc({
			method: 'cardmasters_app.cardmasters_app.api.material_request.make_batched_material_transfer',
			frm
		});
	}, __('Create'));
}

function add_material_request_artist_card_button(frm) {
	frm.add_custom_button(__('Artist Card'), async () => {
		const sales_order = get_linked_sales_order(frm);
		const values = {
			material_request: frm.doc.name,
			sales_order,
			company: frm.doc.company,
			date_created: frappe.datetime.get_today(),
			deadline: get_material_request_deadline(frm),
			project: get_material_request_project(frm)
		};

		if (sales_order) {
			try {
				const sales_order_doc = await frappe.db.get_doc('Sales Order', sales_order);
				Object.assign(values, {
					customer: sales_order_doc.customer,
					deadline: sales_order_doc.delivery_date || values.deadline,
					rush_order: sales_order_doc.custom_rush_order,
					custom_blue_order: sales_order_doc.custom_blue_order,
					project: sales_order_doc.project || values.project,
					branch: sales_order_doc.branch,
					production_branch: sales_order_doc.custom_production_branch
				});
			} catch (error) {
				frappe.show_alert({
					message: __('Some Sales Order details could not be loaded.'),
					indicator: 'orange'
				});
			}
		}

		frappe.new_doc('Artist Card', remove_empty_values(values));
	}, __('Create'));
}

function get_linked_sales_order(frm) {
	if (frm.doc.custom_sales_order) {
		return frm.doc.custom_sales_order;
	}

	const linked_row = (frm.doc.items || []).find(row => row.sales_order);
	return linked_row ? linked_row.sales_order : null;
}

function get_material_request_deadline(frm) {
	const schedule_dates = (frm.doc.items || [])
		.map(row => row.schedule_date)
		.filter(Boolean)
		.sort();

	return schedule_dates[0] || frm.doc.schedule_date;
}

function get_material_request_project(frm) {
	const project_row = (frm.doc.items || []).find(row => row.project);
	return project_row ? project_row.project : null;
}

function remove_empty_values(values) {
	return Object.fromEntries(
		Object.entries(values).filter(([, value]) => value !== undefined && value !== null && value !== '')
	);
}

function add_material_request_work_order_button(frm) {
	frm.add_custom_button(__('Work Order'), () => {
		make_work_order_from_material_request(frm);
	}, __('Create'));
}

async function make_work_order_from_material_request(frm) {
	const rows = get_manufacturable_material_request_rows(frm);

	if (!rows.length) {
		frappe.msgprint(__('There are no Material Request rows available for Work Order creation.'));
		return;
	}

	if (rows.length === 1) {
		await open_work_order_from_material_request_row(frm, rows[0]);
		return;
	}

	const row_options = rows.map(row => {
		const qty = flt(row.stock_qty || row.qty) - flt(row.ordered_qty);
		return `${row.idx}. ${row.item_code} (${qty})`;
	});

	const dialog = new frappe.ui.Dialog({
		title: __('Select Material Request Item'),
		fields: [
			{
				fieldname: 'material_request_item',
				fieldtype: 'Select',
				label: __('Material Request Item'),
				options: row_options.join('\n'),
				reqd: 1
			}
		],
		primary_action_label: __('Create Work Order'),
		async primary_action(values) {
			dialog.hide();
			const selected_index = row_options.indexOf(values.material_request_item);
			await open_work_order_from_material_request_row(frm, rows[selected_index]);
		}
	});

	dialog.show();
}

function get_manufacturable_material_request_rows(frm) {
	return (frm.doc.items || []).filter(row => {
		const pending_qty = flt(row.stock_qty || row.qty) - flt(row.ordered_qty);
		return row.item_code && pending_qty > 0;
	});
}

async function open_work_order_from_material_request_row(frm, row) {
	await with_doctype('Work Order');

	const defaults = await get_material_request_item_work_order_defaults(frm.doc.name, row.name);
	const work_order = frappe.model.get_new_doc('Work Order');

	if (!defaults.bom_no) {
		frappe.show_alert({
			message: __('No submitted default BOM was found for {0}.', [defaults.item_code || row.item_code]),
			indicator: 'orange'
		});
	}

	set_work_order_value(work_order, 'company', defaults.company);
	set_work_order_value(work_order, 'production_item', defaults.item_code);
	set_work_order_value(work_order, 'item_name', defaults.item_name);
	set_work_order_value(work_order, 'qty', defaults.qty);
	set_work_order_value(work_order, 'fg_warehouse', defaults.fg_warehouse);
	set_work_order_value(work_order, 'wip_warehouse', defaults.wip_warehouse);
	set_work_order_value(work_order, 'description', defaults.description);
	set_work_order_value(work_order, 'stock_uom', defaults.stock_uom);
	set_work_order_value(work_order, 'expected_delivery_date', defaults.expected_delivery_date);
	set_work_order_value(work_order, 'sales_order', defaults.sales_order);
	set_work_order_value(work_order, 'sales_order_item', defaults.sales_order_item);
	set_work_order_value(work_order, 'bom_no', defaults.bom_no);
	set_work_order_value(work_order, 'material_request', defaults.material_request);
	set_work_order_value(work_order, 'material_request_item', defaults.material_request_item);
	set_work_order_value(work_order, 'planned_start_date', defaults.transaction_date);
	set_work_order_value(work_order, 'project', defaults.project);
	set_work_order_value(work_order, 'custom_production_type', defaults.custom_production_type);
	set_work_order_value(work_order, 'custom_document', 'Material Request');
	set_work_order_value(work_order, 'custom_document_id', defaults.material_request);
	set_work_order_value(work_order, 'custom_document_item_id', defaults.material_request_item);
	set_work_order_value(work_order, 'custom_item_specifics', defaults.custom_item_specifics);
	set_work_order_value(work_order, 'custom_customer', defaults.custom_customer);

	frappe.set_route('Form', 'Work Order', work_order.name);
}

async function get_material_request_item_work_order_defaults(material_request, material_request_item) {
	const response = await frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.work_order.get_material_request_item_work_order_defaults',
		args: {
			material_request,
			material_request_item
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

function with_doctype(doctype) {
	return new Promise(resolve => {
		frappe.model.with_doctype(doctype, resolve);
	});
}
