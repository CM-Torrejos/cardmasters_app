const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function load(script, frappe) {
	const context = vm.createContext({ frappe, __: text => text, console, setTimeout });
	vm.runInContext(fs.readFileSync(path.join(__dirname, '..', script), 'utf8'), context);
	return context;
}

function workOrderForm(docstatus = 0) {
	return {
		doc: { docstatus, material_request: 'MR-1', material_request_item: 'MRI-1',
			production_item: 'ITEM-1', custom_particulars: 'Saved Work Order particulars' },
		changes: [],
		set_value(field, value) { this.changes.push(field); this.doc[field] = value; }
	};
}

const source = { custom_for_branch: 'Branch', items: [{ name: 'MRI-1',
	item_code: 'ITEM-1', custom_particulars: 'Material Request particulars' }] };

test('Material Request defaults never dirty submitted or cancelled Work Orders', async () => {
	let fetches = 0;
	const context = load('work_order.js', {
		ui: { form: { on() {} } },
		db: { get_doc: async () => { fetches++; return source; } }
	});
	for (const status of [1, 2]) {
		const frm = workOrderForm(status);
		await context.pull_material_request_details(frm);
		assert.equal(frm.doc.custom_particulars, 'Saved Work Order particulars');
		assert.deepEqual(frm.changes, []);
	}
	assert.equal(fetches, 0);
});

test('draft Work Orders still inherit Material Request particulars and branch', async () => {
	const context = load('work_order.js', {
		ui: { form: { on() {} } }, db: { get_doc: async () => source }
	});
	const frm = workOrderForm();
	await context.pull_material_request_details(frm);
	assert.equal(frm.doc.custom_particulars, source.items[0].custom_particulars);
	assert.equal(frm.doc.custom_for_branch, 'Branch');
});

test('pending default lookup cannot overwrite a submitted, reloaded, or relinked form', async () => {
	for (const change of [
		frm => { frm.doc.docstatus = 1; },
		frm => { frm.doc = { ...frm.doc }; },
		frm => { frm.doc.material_request = 'MR-2'; }
	]) {
		let resolve;
		const context = load('work_order.js', {
			ui: { form: { on() {} } }, db: { get_doc: () => new Promise(done => { resolve = done; }) }
		});
		const frm = workOrderForm();
		const pending = context.pull_material_request_details(frm);
		change(frm);
		resolve(source);
		await pending;
		assert.deepEqual(frm.changes, []);
	}
});

test('confirming Material Request discrepancy sends one confirmed retry and reloads', async () => {
	let dialog, confirmation, reloads = 0;
	const requests = [];
	const context = load('material_request.js', {
		ui: { form: { on() {} }, Dialog: class {
			constructor(options) { Object.assign(this, options); dialog = this; }
			show() {} hide() { this.hidden = true; }
			disable_primary_action() {} enable_primary_action() {}
		} },
		model: { can_create: () => true }, get_meta: () => ({ fields: [] }),
		call: async ({ args }) => {
			// Frappe's form-encoded request arrives as strings, including booleans.
			const flag = String(args.confirm_work_orders);
			requests.push(flag);
			return { message: flag === '1' ? { updated: true } : { confirmation_required: true, message: 'Confirm' } };
		},
		confirm: (_, yes) => { confirmation = yes; }, show_alert() {}
	});
	const frm = { is_dirty: () => false, doc: { name: 'MR-1', modified: 'original', items: [] },
		reload_doc: async () => { reloads++; } };
	context.show_material_request_update_details(frm);
	dialog.primary_action({ items: [{ docname: 'MRI-1', custom_particulars: 'Changed' }] });
	await new Promise(setImmediate);
	assert.equal(reloads, 0);
	await confirmation();
	assert.deepEqual(requests, ['0', '1']);
	assert.equal(reloads, 1);
	assert.equal(dialog.hidden, true);
});

test('Quotation replaces only its own editor and restricts it to writable open submissions', () => {
	let events;
	load('quotation.js', { ui: { form: { on(doctype, handlers) {
		assert.equal(doctype, 'Quotation'); events = handlers;
	} } } });
	for (const [docstatus, status, write, expected] of [
		[1, 'Open', true, 1], [1, 'Partially Ordered', true, 1],
		[0, 'Draft', true, 0], [2, 'Cancelled', true, 0],
		[1, 'Ordered', true, 0], [1, 'Lost', true, 0], [1, 'Open', false, 0]
	]) {
		const added = [], removed = [];
		events.refresh({ doc: { docstatus, status }, has_perm: () => write,
			add_custom_button: label => added.push(label), remove_custom_button: label => removed.push(label) });
		assert.equal(added.length, expected);
		assert.ok(removed.includes('Update Items'));
	}
});

test('Quotation sends particulars without deprecated specifics and reloads only after success', async () => {
	let dialog, request, reloads = 0, failure = true;
	const context = load('quotation.js', {
		ui: { form: { on() {} }, Dialog: class {
			constructor(options) { Object.assign(this, options); dialog = this; }
			show() {} hide() { this.hidden = true; }
			disable_primary_action() {} enable_primary_action() {}
		} },
		model: { can_create: () => true }, get_meta: () => ({ fields: [] }),
		call: async options => { request = options; return failure ? { exc: 'failed' } : { message: { updated: true } }; },
		show_alert() {}
	});
	const frm = { is_dirty: () => false, doc: { name: 'QTN-1', modified: 'original',
		items: [{ name: 'ROW-1', item_code: 'ITEM-1', custom_particulars: 'Old particulars', custom_item_specifics: 'Legacy value' }] },
		reload_doc: async () => { reloads++; } };
	context.show_quotation_update_details(frm);
	assert.equal(dialog.fields[0].data[0].custom_particulars, 'Old particulars');
	assert.equal(dialog.fields[0].data[0].custom_item_specifics, undefined);
	assert.ok(!dialog.fields[0].fields.some(field => field.fieldname === 'custom_item_specifics'));
	const values = { items: [{ docname: 'ROW-1', custom_particulars: ' New particulars ' }] };
	dialog.primary_action(values);
	await new Promise(setImmediate);
	assert.equal(reloads, 0);
	assert.ok(!dialog.hidden);
	failure = false;
	dialog.primary_action(values);
	await new Promise(setImmediate);
	assert.equal(request.method, 'cardmasters_app.cardmasters_app.api.quotation.update_details');
	assert.equal(request.args.modified, 'original');
	assert.equal(request.args.items[0].custom_particulars, 'New particulars');
	assert.equal(request.args.items[0].custom_item_specifics, undefined);
	assert.equal(reloads, 1);
	assert.equal(dialog.hidden, true);
});


test('Quotation removes Update Items after the legacy controller and preserves custom refresh', async () => {
	let events, previousCalls = 0;
	load('quotation.js', { ui: { form: { on(doctype, handlers) { events = handlers; } } } });
	const buttons = new Set(['Update Details']);
	const frm = {
		cscript: { async custom_refresh() { previousCalls++; buttons.add('Update Items'); } },
		remove_custom_button(label) { buttons.delete(label); }
	};
	events.setup(frm);
	for (let refresh = 0; refresh < 2; refresh++) {
		buttons.add('Update Items');
		await frm.cscript.custom_refresh();
		assert.deepEqual([...buttons], ['Update Details']);
	}
	assert.equal(previousCalls, 2);
});
