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
