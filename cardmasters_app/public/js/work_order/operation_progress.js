frappe.ui.form.on('Work Order', {
	setup(frm) {
		$(frm.wrapper).on('grid-row-render.cardmasters-progress', (event, row) => {
			render_submitted_operation_progress(frm, row);
		});
	},
	refresh(frm) {
		(frm.fields_dict.operations?.grid.grid_rows || []).forEach(row => {
			render_submitted_operation_progress(frm, row);
		});
	}
});

frappe.ui.form.on('Work Order Operation', {
	custom_progress(frm, cdt, cdn) {
		const row = frm.fields_dict.operations?.grid.grid_rows_by_docname[cdn];
		if (row) render_submitted_operation_progress(frm, row);
	}
});

function render_submitted_operation_progress(frm, row) {
	if (row.grid !== frm.fields_dict.operations?.grid || !row.doc) return;
	const column = row.columns.custom_progress;
	if (!column) return;

	column.children('.cardmasters-operation-progress').remove();
	const df = column.df;
	if (
		frm.doc.docstatus !== 1 || frm.read_only ||
		row.grid.is_editable() || df.fieldtype !== 'Select' || !Number(df.allow_on_submit) ||
		frappe.perm.get_field_display_status(df, row.doc, frm.perm) !== 'Write'
	) {
		column.static_area.toggle(!df.hidden && !df.hidden_due_to_dependency);
		return;
	}

	// Submitted grids block inline controls even when the child allows updates.
	// Bind a normal document control without the parent grid's read-only override.
	// Frappe still handles field permissions, model events, dirty state and saving.
	const parent = $('<div class="cardmasters-operation-progress"></div>').appendTo(column);
	parent.on('click keydown', event => event.stopPropagation());
	const control = frappe.ui.form.make_control({
		df: { ...df },
		parent,
		only_input: true,
		frm,
		doc: row.doc,
		doctype: row.doc.doctype,
		docname: row.doc.name
	});
	control.refresh();
	control.$input?.addClass('input-sm').attr('aria-label', __(df.label));
	column.static_area.hide();
}
