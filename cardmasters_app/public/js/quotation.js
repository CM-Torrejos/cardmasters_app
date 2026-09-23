// Keep the Sales Order and shared item-editor overrides independent of Quotation.
frappe.ui.form.on('Quotation', {
	setup(frm) {
		// Legacy controller refresh runs after form refresh handlers and adds Update Items again.
		const previous_refresh = frm.cscript.custom_refresh;
		frm.cscript.custom_refresh = async function (...args) {
			if (previous_refresh) await previous_refresh.apply(this, args);
			frm.remove_custom_button(__('Update Items'));
			frm.remove_custom_button(__('Update Items'), __('Update'));
		};
	},
	refresh(frm) {
		frm.remove_custom_button(__('Update Items'));
		frm.remove_custom_button(__('Update Details'));
		if (frm.doc.docstatus === 1 && !['Lost', 'Ordered', 'Cancelled'].includes(frm.doc.status)
			&& frm.has_perm('write')) {
			frm.add_custom_button(__('Update Details'), () => show_quotation_update_details(frm));
		}
	}
});

function show_quotation_update_details(frm) {
	if (frm.is_dirty()) {
		frappe.msgprint(__('Save your changes before updating details.'));
		return;
	}
	const meta = frappe.get_meta('Quotation Item');
	const precision = fieldname => meta.fields.find(field => field.fieldname === fieldname)?.precision;
	const editable_fields = ['qty', 'rate', 'uom', 'conversion_factor',
		'custom_particulars'];
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
			cannot_add_rows: !frappe.model.can_create('Quotation'), cannot_delete_rows: false,
			in_place_edit: false, data,
			fields: [
				{ fieldname: 'docname', fieldtype: 'Data', hidden: 1, read_only: 1 },
				{
					fieldname: 'item_code', fieldtype: 'Link', options: 'Item', label: __('Item Code'),
					reqd: 1, read_only_depends_on: 'eval:!!doc.docname', in_list_view: 1,
					get_query: () => ({ query: 'erpnext.controllers.queries.item_query', filters: { is_sales_item: 1 } }),
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
									doctype: 'Quotation', name: frm.doc.name, item_code,
									company: frm.doc.company, quotation_to: frm.doc.quotation_to,
									customer: frm.doc.party_name, currency: frm.doc.currency,
									conversion_rate: frm.doc.conversion_rate, price_list: frm.doc.selling_price_list,
									price_list_currency: frm.doc.price_list_currency, plc_conversion_rate: frm.doc.plc_conversion_rate,
									transaction_date: frm.doc.transaction_date, qty: row.qty || 1,
									set_warehouse: frm.doc.set_warehouse, ignore_pricing_rule: frm.doc.ignore_pricing_rule
								} }
							});
							if (row.item_code === item_code && response.message) {
								const defaults = response.message;
								Object.assign(row, {
									uom: defaults.uom || defaults.stock_uom,
									conversion_factor: defaults.conversion_factor || 1,
									rate: defaults.rate ?? defaults.price_list_rate ?? 0
								});
								dialog.fields_dict.items.grid.refresh();
							}
						} finally {
							pending_item_lookups--;
						}
					}
				},
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
				custom_particulars: String(row.custom_particulars || '').trim()
			}));
			update(items);
		}
	});
	async function update(items) {
		if (saving) return;
		saving = true;
		dialog.disable_primary_action();
		try {
			const response = await frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.quotation.update_details',
				args: { quotation: frm.doc.name, items, modified },
				freeze: true, freeze_message: __('Updating Quotation details...')
			});
			if (response.exc) return;
			dialog.hide();
			await frm.reload_doc();
			frappe.show_alert({ message: __('Quotation details updated.'), indicator: 'green' });
		} finally {
			saving = false;
			dialog.enable_primary_action();
		}
	}
	dialog.show();
}
