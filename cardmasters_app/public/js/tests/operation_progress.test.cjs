const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function fixture() {
	const handlers = {}, controls = [];
	const element = {
		appendTo() { return this; }, on() { return this; },
		addClass() { return this; }, attr() { return this; }
	};
	const column = {
		df: { fieldname: 'custom_progress', fieldtype: 'Select', allow_on_submit: 1,
			label: 'Progress', options: 'Not Started\nIn Progress\nOn Hold\nDone' },
		children: () => ({ remove() {} }),
		static_area: { hide() {}, toggle() {} }
	};
	const grid = { is_editable: () => false };
	const row = { grid, doc: { doctype: 'Work Order Operation', name: 'OP-1', docstatus: 1 },
		columns: { custom_progress: column } };
	grid.grid_rows = [row];
	grid.grid_rows_by_docname = { 'OP-1': row };
	const frm = { doc: { docstatus: 1 }, perm: [{ write: 1 }], fields_dict: { operations: { grid } } };
	const frappe = {
		perm: { get_field_display_status: (df, doc, perm) => perm[0].write && !df.read_only ? 'Write' : 'Read' },
		ui: { form: {
			on: (doctype, events) => { handlers[doctype] = events; },
			make_control: args => {
				controls.push(args);
				return { refresh() {}, $input: element };
			}
		} }
	};
	const context = vm.createContext({ frappe, $: () => element, __: value => value });
	vm.runInContext(fs.readFileSync(path.join(__dirname, '../work_order/operation_progress.js'), 'utf8'), context);
	return { handlers, controls, frm, row, column, grid };
}

test('submitted Progress binds to the child document and refreshes after changes', () => {
	const { handlers, controls, frm, row, column } = fixture();
	handlers['Work Order'].refresh(frm);
	assert.equal(controls.length, 1);
	assert.equal(controls[0].doc, row.doc);
	assert.equal(controls[0].frm, frm);
	assert.equal(controls[0].docname, 'OP-1');
	assert.equal(controls[0].grid, undefined);
	assert.equal(controls[0].df.options, column.df.options);
	assert.notEqual(controls[0].df, column.df);
	handlers['Work Order Operation'].custom_progress(frm, row.doc.doctype, 'OP-1');
	assert.equal(controls.length, 2);
});

test('does not bypass document state, field permissions, or enable other grids', () => {
	for (const change of [
		f => { f.frm.doc.docstatus = 0; },
		f => { f.frm.doc.docstatus = 2; },
		f => { f.frm.read_only = true; },
		f => { f.frm.perm[0].write = 0; },
		f => { f.column.df.read_only = 1; },
		f => { f.column.df.allow_on_submit = 0; },
		f => { f.column.df.fieldtype = 'Data'; },
		f => { f.grid.is_editable = () => true; },
		f => { f.row.grid = {}; }
	]) {
		const f = fixture();
		change(f);
		f.handlers['Work Order'].refresh(f.frm);
		assert.equal(f.controls.length, 0);
	}
});
