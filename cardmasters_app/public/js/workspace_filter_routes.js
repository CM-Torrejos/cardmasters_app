// Workspace shortcuts and quick lists convert saved filters into route options.
// Keep the DocType: different child tables can have the same field name.
(() => {
	const original = frappe.utils.get_filter_from_json;
	frappe.utils.get_filter_from_json = function (filter_json, doctype) {
		// Filter editors need the original array format, including legacy conversion.
		if (doctype || !filter_json || !filter_json.length) {
			return original.call(this, filter_json, doctype);
		}

		const filters = this.process_filter_expression(filter_json);
		if (!Array.isArray(filters)) {
			return filters || [];
		}

		return Object.fromEntries(filters.map(([filter_doctype, field, operator, value]) => [
			filter_doctype && !field.includes(".") ? `${filter_doctype}.${field}` : field,
			[operator, value],
		]));
	};
})();
