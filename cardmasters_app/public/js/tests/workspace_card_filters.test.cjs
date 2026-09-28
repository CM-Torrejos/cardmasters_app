const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function fixture() {
	const dialogs = [];
	class Dialog {
		constructor(opts) { Object.assign(this, opts); this.values = {}; this.fields_dict = {}; dialogs.push(this); this.make(); }
		make() {
			for (const df of this.fields || []) this.fields_dict[df.fieldname] = { df,
				$wrapper: { empty() { return this; } },
				grid: { get_data: () => df.data, refresh() {} },
			};
		}
		show() {}
		hide() { this.hidden = true; }
		get_field(name) { return this.fields_dict[name]; }
		get_value(name) { return this.values[name]; }
		set_value(name, value) { this.values[name] = value; return this.fields_dict[name].df.onchange?.(); }
	}
	class LinksWidget {
		set_body() {
			this.link_list = this.links.map(item => ({
				href: '/app/sales-order',
				attr(key, value) { if (value !== undefined) this.href = value; return this.href; },
				hasClass: () => !!item.disabled,
			}));
		}
	}
	const frappe = {
		count_calls: [],
		ui: { Dialog }, boot: { single_types: ['System Settings'] },
		filter_groups: [], run_serially: tasks => tasks.reduce((p, task) => p.then(task), Promise.resolve()),
		model: { with_doctype: async () => {} }, dialogs,
		widget: { widget_factory: { links: LinksWidget } },
		utils: { process_filter_expression: JSON.parse, get_filter_from_json: JSON.parse,
			generate_route: () => '/app/sales-order/view/list' },
	};
	frappe.db = { count: async (doctype, args) => { frappe.count_calls.push({ doctype, args }); return 12; } };
	const $ = () => ({
		addClass(value) { this.classes = value; return this; },
		css() { return this; }, text(value) { this.label = value; return this; },
		attr() { return this; }, appendTo(link) { link.badge = this; return this; },
	});
	const context = { frappe, $, __: s => s, URL, window: { location: { origin: 'http://localhost' } }, console };
	// Use the installed Frappe methods: add_filters() assumes a popover button,
	// whereas this feature embeds an inline FilterGroup without that button.
	const corePath = path.resolve(__dirname, '../../../../../frappe/frappe/public/js/frappe/ui/filters/filter_list.js');
	vm.runInNewContext(fs.readFileSync(corePath, 'utf8'), context);
	const NativeFilterGroup = frappe.ui.FilterGroup;
	frappe.ui.FilterGroup = function () {
		const group = Object.create(NativeFilterGroup.prototype);
		group.filters = [];
		group.add_filter = async (...values) => {
			group.filters.push({ field: {}, get_value: () => values, get_selected_value: () => values[3] });
		};
		group.toggle_empty_filters = () => {};
		frappe.filter_groups.push(group);
		return group;
	};
	for (const file of ['workspace_filter_routes.js', 'workspace_card_filters.js']) {
		vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', file), 'utf8'), context);
	}
	return frappe;
}

test('filtered links encode child table, operators and special characters into real URLs', () => {
	const frappe = fixture();
	const widget = new frappe.widget.widget_factory.links();
	widget.links = [{ link_type: 'DocType', link_to: 'Sales Order', custom_card_filters: JSON.stringify([
		['Sales Order', 'customer', '=', 'A&B "Company"'],
		['Sales Order Item', 'item_code', 'in', ['ONE', 'TWO']],
		['Sales Order', 'grand_total', '>=', 100],
		['Sales Order', 'grand_total', '<=', 500],
	]) }];
	widget.set_body();
	const url = new URL(widget.link_list[0].href, 'http://localhost');
	assert.equal(url.pathname, '/app/sales-order/view/list');
	assert.deepEqual(JSON.parse(url.searchParams.get('Sales Order.customer')), ['=', 'A&B "Company"']);
	assert.deepEqual(JSON.parse(url.searchParams.get('Sales Order Item.item_code')), ['in', ['ONE', 'TWO']]);
	assert.deepEqual(url.searchParams.getAll('Sales Order.grand_total').map(JSON.parse), [['>=', 100], ['<=', 500]]);
});

test('filter editor preserves independent duplicate links through switching and applying', async () => {
	const frappe = fixture();
	const rows = ['Draft', 'Completed'].map(status => ({
		link_type: 'DocType', link_to: 'Sales Order', label: status,
		custom_card_filters: JSON.stringify([['Sales Order', 'status', '=', status]]),
	}));
	const original = rows.map(row => row.custom_card_filters);
	const card = new frappe.ui.Dialog({ fields: [{ fieldname: 'links', fieldtype: 'Table', data: rows,
		fields: [{ fieldname: 'link_type' }, { fieldname: 'link_to' }],
	}] });
	card.fields[1].click();
	const editor = frappe.dialogs.at(-1);
	await new Promise(resolve => setImmediate(resolve));
	await frappe.filter_groups.at(-1).add_filter('Sales Order', 'customer', '=', 'Test Customer');
	editor.set_value('custom_card_show_count', 1);
	editor.set_value('custom_card_count_color', 'Red');
	await editor.set_value('card_link', '1');
	assert.equal(editor.get_value('custom_card_show_count'), 0);
	editor.set_value('custom_card_show_count', 1);
	editor.set_value('custom_card_count_color', 'Green');
	// Changes remain staged until Apply.
	assert.deepEqual(rows.map(row => row.custom_card_filters), original);
	editor.primary_action();
	assert.equal(editor.hidden, true);
	assert.deepEqual(JSON.parse(rows[0].custom_card_filters), [
		['Sales Order', 'status', '=', 'Draft'], ['Sales Order', 'customer', '=', 'Test Customer'],
	]);
	assert.equal(rows[1].custom_card_filters, original[1]);
	assert.equal(rows[0].custom_card_show_count, 1);
	assert.equal(rows[0].custom_card_count_color, 'Red');
	assert.equal(rows[1].custom_card_count_color, 'Green');
});

test('count badges use the exact filters and chosen color, including zero and unfiltered totals', async () => {
	const frappe = fixture();
	const filters = [['Sales Order Item', 'item_code', 'in', ['ONE', 'TWO']]];
	const widget = new frappe.widget.widget_factory.links();
	widget.links = [{ link_type: 'DocType', link_to: 'Sales Order', custom_card_show_count: 1,
		custom_card_count_color: 'Red', custom_card_filters: JSON.stringify(filters) }];
	widget.set_body();
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(frappe.count_calls[0].doctype, 'Sales Order');
	assert.deepEqual(frappe.count_calls[0].args.filters, filters);
	assert.equal(widget.link_list[0].badge.label, 12);
	assert.match(widget.link_list[0].badge.classes, / red$/);
	frappe.db.count = async (doctype, { filters }) => { assert.deepEqual(filters, []); return 0; };
	widget.links[0].custom_card_filters = '';
	widget.set_body();
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(widget.link_list[0].badge.label, 0);
	assert.match(widget.link_list[0].badge.classes, / gray$/);
});

test('counts remain opt-in and are skipped for reports, singles, disabled links and customization', () => {
	const frappe = fixture();
	const widget = new frappe.widget.widget_factory.links();
	widget.links = [
		{ link_type: 'DocType', link_to: 'Sales Order' },
		{ link_type: 'Report', link_to: 'General Ledger', custom_card_show_count: 1 },
		{ link_type: 'DocType', link_to: 'System Settings', custom_card_show_count: 1 },
		{ link_type: 'DocType', link_to: 'Sales Order', custom_card_show_count: 1, disabled: true },
	];
	widget.set_body();
	assert.equal(frappe.count_calls.length, 0);
	widget.in_customize_mode = true;
	widget.links[0].custom_card_show_count = 1;
	widget.set_body();
	assert.equal(frappe.count_calls.length, 0);
});

test('ordinary, report, single and disabled links retain their original destination', () => {
	const frappe = fixture();
	for (const item of [{}, { custom_card_filters: '[]' }, { link_type: 'Report' },
		{ link_to: 'System Settings' }, { disabled: true }]) {
		const widget = new frappe.widget.widget_factory.links();
		widget.links = [{ link_type: 'DocType', link_to: 'Sales Order',
			custom_card_filters: '[["Sales Order","status","=","Draft"]]', ...item }];
		if (!Object.keys(item).length) delete widget.links[0].custom_card_filters;
		widget.set_body();
		assert.equal(widget.link_list[0].href, '/app/sales-order');
	}
});

test('a new link can apply filters, reopen them, and clear them', async () => {
	const frappe = fixture();
	const row = { link_type: 'DocType', link_to: 'Sales Order' };
	const card = new frappe.ui.Dialog({ fields: [{ fieldname: 'links', fieldtype: 'Table', data: [row],
		fields: [{ fieldname: 'link_type' }, { fieldname: 'link_to' }],
	}] });
	card.fields[1].click();
	await new Promise(resolve => setImmediate(resolve));
	await frappe.filter_groups.at(-1).add_filter('Sales Order', 'status', '=', 'Draft');
	frappe.dialogs.at(-1).primary_action();
	assert.equal(frappe.dialogs.at(-1).hidden, true);
	assert.deepEqual(JSON.parse(row.custom_card_filters), [['Sales Order', 'status', '=', 'Draft']]);
	card.fields[1].click();
	await new Promise(resolve => setImmediate(resolve));
	assert.equal(frappe.filter_groups.at(-1).get_filters()[0][3], 'Draft');
	frappe.filter_groups.at(-1).filters = [];
	frappe.dialogs.at(-1).primary_action();
	assert.equal(frappe.dialogs.at(-1).hidden, true);
	assert.equal(row.custom_card_filters, '[]');
});

test('only card dialogs receive the editor and changing target clears stale filters', () => {
	const frappe = fixture();
	const other = new frappe.ui.Dialog({ fields: [{ fieldname: 'title', fieldtype: 'Data' }] });
	assert.equal(other.fields.length, 1);
	let originalCalled = false;
	const table = { fieldname: 'links', fieldtype: 'Table', fields: [
		{ fieldname: 'link_type' },
		{ fieldname: 'link_to', onchange() { originalCalled = true; } },
	] };
	const card = new frappe.ui.Dialog({ fields: [table] });
	assert.equal(card.fields[1].fieldname, 'edit_card_link_filters');
	assert.ok(table.fields.some(df => df.fieldname === 'custom_card_filters'));
	const doc = { custom_card_filters: '[["Sales Order","status","=","Draft"]]' };
	table.fields[1].onchange.call({ doc });
	assert.equal(doc.custom_card_filters, '[]');
	assert.equal(originalCalled, true);
});
