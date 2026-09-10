// Run with: node --test cardmasters_app/cardmasters_app/report/production_tower/test_production_tower_sort.cjs
// Exercise the installed DataTable data/tree/render code; stub only browser DOM/virtual scrolling.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');
const src = path.join(path.dirname(require.resolve('frappe-datatable/package.json', {
    paths: [path.resolve(__dirname, '../../../../../frappe')]
})), 'src');

function setup(data) {
    const context = vm.createContext({
        frappe: { query_reports: {} }, setTimeout, console,
        _throttle: fn => fn, _debounce: fn => fn, _uniq: values => [...new Set(values)],
        $: { on() {} }, getComputedStyle: () => ({ width: '100px', height: '100px' }),
        HyperList: class { constructor(_, config) { this.config = config; } refresh(_, config) { this.config = config; } }
    });
    for (const [file, name] of [['utils', null], ['datamanager', 'DataManager'],
        ['rowmanager', 'RowManager'], ['body-renderer', 'BodyRenderer']]) {
        let source = fs.readFileSync(path.join(src, `${file}.js`), 'utf8')
            .replace(/^import\s[\s\S]*?;\n/gm, '').replace(/export default /g, '').replace(/export /g, '');
        if (name) source += `\nglobalThis.${name} = ${name};`;
        vm.runInContext(source, context);
    }
    vm.runInContext(fs.readFileSync(path.join(__dirname, 'production_tower.js'), 'utf8'), context);
    const fields = ['label_name', 'date', 'workflow_state', 'completion_rate', 'qty', 'wo_status', 'produced_qty', 'is_bypass'];
    const options = {
        columns: fields.map(id => ({ id, fieldname: id, name: id })),
        data, serialNoColumn: true, checkboxColumn: false, treeView: true,
        filterRows: rows => rows.map(row => row.meta.rowIndex)
    };
    const dm = new context.DataManager(options);
    dm.init();
    const table = { options, datamanager: dm, bodyScrollable: {}, footer: {},
        setDimensions() {}, renderBody() { this.bodyRenderer.render(); } };
    table.rowmanager = new context.RowManager(table);
    table.bodyRenderer = new context.BodyRenderer(table);
    table.bodyRenderer.getNoDataHTML = () => '';
    table.bodyRenderer.render();
    const install = context.frappe.query_reports['Production Tower'].after_datatable_render;
    install(table);
    return {
        table, dm, install,
        order: () => Array.from(dm.rowViewOrder, i => dm.data[i].key),
        visible: () => Array.from(table.bodyRenderer.visibleRows, row => dm.data[row.meta.rowIndex].key),
        async sort(field, direction) {
            await dm.sortRows(dm.getColumnIndexById(field), direction);
            await table.rowmanager.refreshRows();
        }
    };
}

function fixture() {
    return [
        { key: 'A', indent: 0, label_name: 'SO-10', date: '2026-10-01', workflow_state: 'Queued', completion_rate: '100%', qty: '8 / 10', is_bypass: 1 },
        { key: 'A1', indent: 1, label_name: 'Same item', completion_rate: '100%', qty: '100 / 100', produced_qty: 100, is_bypass: 1 },
        { key: 'A11', indent: 2, label_name: 'WO-10', completion_rate: '100%', qty: 90, produced_qty: 90, wo_status: 'Completed', is_bypass: 1 },
        { key: 'A12', indent: 2, label_name: 'WO-2', completion_rate: '9%', qty: 10, produced_qty: 0.9, wo_status: 'Not Started', is_bypass: 0 },
        { key: 'A2', indent: 1, label_name: 'Same item', completion_rate: '9%', qty: '1 / 2', produced_qty: 0, is_bypass: 0 },
        { key: 'A21', indent: 2, label_name: 'WO-1', completion_rate: '0%', qty: 1, produced_qty: 0, wo_status: 'In Process', is_bypass: 0 },
        { key: 'B', indent: 0, label_name: 'SO-2', date: '2026-09-01', workflow_state: 'Active', completion_rate: '9%', qty: '1 / 2', is_bypass: 0 },
        { key: 'B1', indent: 1, label_name: 'Same item', completion_rate: '0%', qty: '0 / 2', produced_qty: 0, is_bypass: 0 },
        { key: 'B11', indent: 2, label_name: 'WO-3', completion_rate: '0%', qty: 2, produced_qty: 0, wo_status: 'Draft', is_bypass: 0 },
        { key: 'C', indent: 0, label_name: 'SO-3', completion_rate: '0%', qty: '0 / 0', is_bypass: 0 }
    ];
}

function assertHierarchy(s) {
    const parent = new Map();
    const stack = [];
    s.dm.data.forEach((row, i) => {
        while (stack.length && s.dm.data[stack.at(-1)].indent >= row.indent) stack.pop();
        parent.set(i, stack.at(-1));
        stack.push(i);
    });
    const seen = new Set();
    stack.length = 0;
    for (const i of s.dm.rowViewOrder) {
        assert.equal(seen.has(i), false, 'no duplicate rows');
        seen.add(i);
        while (stack.length && s.dm.data[stack.at(-1)].indent >= s.dm.data[i].indent) stack.pop();
        assert.equal(stack.at(-1), parent.get(i), `row ${i} stays in its original branch`);
        stack.push(i);
    }
    assert.equal(seen.size, s.dm.data.length);
}

test('every column preserves branch membership across repeated asc/desc/reset sorts', async () => {
    const s = setup(fixture());
    const originalRows = Array.from(s.dm.rows);
    for (let repeat = 0; repeat < 3; repeat++) {
        for (const column of s.dm.columns) {
            for (const direction of ['desc', 'asc', 'none']) {
                await s.sort(column.id, direction);
                assertHierarchy(s);
                assert.deepEqual(Array.from(s.dm.rows), originalRows, 'row identities remain unchanged');
                assert.deepEqual(s.visible(), s.order(), 'display/export order agrees');
                if (direction === 'none') assert.deepEqual(s.order(), fixture().map(row => row.key));
            }
        }
    }
});

test('natural references and numeric completion, quantities, produced and bypass', async () => {
    const s = setup(fixture());
    await s.sort('label_name', 'asc');
    assert.deepEqual(s.order(), ['B', 'B1', 'B11', 'C', 'A', 'A1', 'A12', 'A11', 'A2', 'A21']);
    await s.sort('completion_rate', 'asc');
    assert.deepEqual(s.order(), ['C', 'B', 'B1', 'B11', 'A', 'A2', 'A21', 'A1', 'A12', 'A11']);
    await s.sort('qty', 'asc');
    assert.deepEqual(s.order(), ['B', 'B1', 'B11', 'A', 'A2', 'A21', 'A1', 'A12', 'A11', 'C']);
    await s.sort('qty', 'desc');
    assert.equal(s.order().at(-1), 'C', 'undefined 0/0 ratio stays last descending');
    await s.sort('produced_qty', 'asc');
    assert.deepEqual(s.order(), ['A', 'A2', 'A21', 'A1', 'A12', 'A11', 'B', 'B1', 'B11', 'C']);
    await s.sort('is_bypass', 'desc');
    assert.equal(s.order()[0], 'A');
    assert.equal(s.order()[2], 'A11');
});

test('level-specific columns leave other levels in original order; missing dates stay last', async () => {
    const s = setup(fixture());
    await s.sort('date', 'asc');
    assert.deepEqual(s.order(), ['B', 'B1', 'B11', 'A', 'A1', 'A11', 'A12', 'A2', 'A21', 'C']);
    await s.sort('date', 'desc');
    assert.equal(s.order().at(-1), 'C');
    await s.sort('workflow_state', 'asc');
    assert.equal(s.order()[0], 'B');
    await s.sort('wo_status', 'desc');
    assert.deepEqual(s.order(), ['A', 'A1', 'A12', 'A11', 'A2', 'A21', 'B', 'B1', 'B11', 'C']);
});

test('fractional planning keys override rounded text; ties ignore previous sorts', async () => {
    const s = setup([
        { key: 'SO', indent: 0 },
        { key: 'one', indent: 1, qty: '1 / 2', _sort_qty: 0.9, label_name: 'Z' },
        { key: 'two', indent: 1, qty: '1 / 2', _sort_qty: 0.6, label_name: 'B' },
        { key: 'three', indent: 1, qty: '1 / 2', _sort_qty: 0.6, label_name: 'A' },
        { key: 'over', indent: 1, qty: '3 / 2', _sort_qty: 1.5 },
        { key: 'zero', indent: 1, qty: '0 / 2', _sort_qty: 0 }
    ]);
    await s.sort('label_name', 'asc');
    await s.sort('qty', 'asc');
    assert.deepEqual(s.order(), ['SO', 'zero', 'two', 'three', 'one', 'over']);
    await s.sort('qty', 'desc');
    assert.deepEqual(s.order(), ['SO', 'over', 'one', 'two', 'three', 'zero']);
});

test('collapse/expand and tree depth preserve sorting and never cross a parent boundary', async () => {
    const s = setup(fixture());
    const rm = s.table.rowmanager;
    await s.sort('label_name', 'desc');
    // Last item of A must not accidentally collect B's work orders.
    assert.deepEqual(Array.from(s.dm.getChildren(4)), [5]);
    assert.deepEqual(Array.from(s.dm.getImmediateChildren(4)), [5]);
    rm.closeSingleNode(4);
    assert.equal(s.visible().includes('B11'), true);
    assert.equal(s.visible().includes('A21'), false);
    rm.closeSingleNode(0);
    await s.sort('qty', 'asc');
    assert.deepEqual(s.visible(), ['B', 'B1', 'B11', 'A', 'C']);
    rm.openSingleNode(0);
    assert.deepEqual(s.visible(), ['B', 'B1', 'B11', 'A', 'A2', 'A1', 'C']);
    rm.openSingleNode(1);
    assert.deepEqual(s.visible(), ['B', 'B1', 'B11', 'A', 'A2', 'A1', 'A12', 'A11', 'C']);
    rm.setTreeDepth(0);
    await s.sort('label_name', 'asc');
    assert.deepEqual(s.visible(), ['B', 'C', 'A']);
    rm.expandAllNodes();
    assert.deepEqual(s.visible(), s.order());
    rm.collapseAllNodes();
    assert.deepEqual(s.visible(), ['B', 'C', 'A']);
});

test('sorting preserves inline-filter visibility, including no matches', async () => {
    const s = setup(fixture());
    s.table.rowmanager.showRows([0, 1, 2, 3]);
    await s.sort('label_name', 'asc');
    assert.deepEqual(s.visible(), ['A', 'A1', 'A12', 'A11']);
    s.table.rowmanager.showRows([]);
    await s.sort('qty', 'desc');
    assert.deepEqual(s.visible(), []);
});

test('report refresh rebuilds branch membership, with no duplicate hook installation', async () => {
    const s = setup(fixture());
    const sorter = s.dm._sortRows;
    const renderer = s.table.bodyRenderer.renderRows;
    s.install(s.table);
    assert.equal(s.dm._sortRows, sorter);
    assert.equal(s.table.bodyRenderer.renderRows, renderer);
    await s.sort('qty', 'desc');
    s.dm.init([{ key: 'new', indent: 0, label_name: 'SO-1' },
        { key: 'child', indent: 1, label_name: 'Item' }]);
    s.table.bodyRenderer.render();
    s.install(s.table);
    await s.sort('label_name', 'desc');
    assert.deepEqual(s.order(), ['new', 'child']);
    assert.deepEqual(s.visible(), ['new', 'child']);
    assert.deepEqual(Array.from(s.dm.getChildren(0)), [1]);
});

test('empty reports can sort and reset', async () => {
    const s = setup([]);
    await s.sort('qty', 'asc');
    await s.sort('qty', 'none');
    assert.deepEqual(s.order(), []);
    assert.deepEqual(s.visible(), []);
});

test('mixed Sales Order and Material Request roots sort together without mixing their items or work orders', async () => {
    const s = setup([
        { key: 'SO', indent: 0, reference_doctype: 'Sales Order', label_name: 'SO-1', date: '2026-09-10', qty: '1 / 1' },
        { key: 'SOI', indent: 1, label_name: 'Repeated item', qty: '10 / 10' },
        { key: 'SOWO', indent: 2, label_name: 'Shared WO', qty: 10 },
        { key: 'MR', indent: 0, reference_doctype: 'Material Request', label_name: '[MR] MR-1', date: '2026-09-01', qty: '1 / 2' },
        { key: 'MRI1', indent: 1, label_name: 'Repeated item', qty: '10 / 10' },
        { key: 'MRWO', indent: 2, label_name: 'Shared WO', qty: 10 },
        { key: 'MRI2', indent: 1, label_name: 'Repeated item', qty: '0 / 10' }
    ]);
    for (const column of s.dm.columns) {
        for (const direction of ['asc', 'desc', 'none']) {
            await s.sort(column.id, direction);
            assertHierarchy(s);
        }
    }
    await s.sort('qty', 'asc');
    assert.deepEqual(s.order(), ['MR', 'MRI2', 'MRI1', 'MRWO', 'SO', 'SOI', 'SOWO']);
    s.table.rowmanager.closeSingleNode(3);
    await s.sort('date', 'asc');
    assert.deepEqual(s.visible(), ['MR', 'SO', 'SOI', 'SOWO']);
});
