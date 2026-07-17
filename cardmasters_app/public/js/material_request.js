frappe.ui.form.on('Material Request', {
	refresh(frm) {
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
