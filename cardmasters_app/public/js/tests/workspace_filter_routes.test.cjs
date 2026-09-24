const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { test } = require('node:test');

function fixture() {
	const calls = [];
	const utils = {
		process_filter_expression: JSON.parse,
		get_filter_from_json(...args) {
			calls.push({ receiver: this, args });
			return 'original-result';
		},
	};
	vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../workspace_filter_routes.js'), 'utf8'), {
		frappe: { utils },
	});
	return { utils, calls };
}

test('Cebu shortcut preserves the operations table and both selected operations', () => {
	const { utils } = fixture();
	const result = utils.get_filter_from_json(JSON.stringify([
		['Work Order Operation', 'operation', 'in', ['LASER CUTTING', 'HEATPRESS'], false],
	]));
	assert.deepEqual(JSON.parse(JSON.stringify(result)), {
		'Work Order Operation.operation': ['in', ['LASER CUTTING', 'HEATPRESS']],
	});
});

test('same-named fields in different child tables do not overwrite each other', () => {
	const { utils } = fixture();
	const result = utils.get_filter_from_json(JSON.stringify([
		['Work Order Item', 'operation', '=', 'LASER CUTTING'],
		['Work Order Operation', 'operation', '=', 'HEATPRESS'],
		['Work Order', 'status', '=', 'Not Started'],
	]));
	assert.deepEqual(Object.keys(result), [
		'Work Order Item.operation', 'Work Order Operation.operation', 'Work Order.status',
	]);
});

test('legacy object filters remain usable as route options', () => {
	const { utils } = fixture();
	const filters = { status: ['=', 'Not Started'] };
	assert.deepEqual(utils.get_filter_from_json(JSON.stringify(filters)), filters);
});

test('editors and empty inputs retain the original converter behavior', () => {
	const { utils, calls } = fixture();
	for (const args of [['[]', 'Work Order'], [''], [null], [undefined], [[]]]) {
		assert.equal(utils.get_filter_from_json(...args), 'original-result');
		assert.equal(calls.at(-1).receiver, utils);
		assert.equal(calls.at(-1).args[0], args[0]);
		assert.equal(calls.at(-1).args[1], args[1]);
	}
});
