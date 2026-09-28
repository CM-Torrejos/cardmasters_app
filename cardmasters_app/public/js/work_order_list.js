(() => {
	const settings = frappe.listview_settings["Work Order"] ||= {};
	const original_refresh = settings.refresh;
	const marker = "cm-operation-progress";
	const colors = { "Not Started": "orange", "In Progress": "blue", "On Hold": "yellow", Done: "green" };
	const operation_filters = list => (list.filter_area?.get() || [])
		.filter(filter => filter[0] === "Work Order Operation")
		.map(filter => filter.slice(0, 4));
	const escape = value => frappe.utils.escape_html(String(value));

	settings.refresh = function (list) {
		original_refresh?.call(this, list);
		const generation = list._cm_operation_generation = (list._cm_operation_generation || 0) + 1;
		list.$result.find(`.${marker}`).remove();
		list.$result.find(".cm-operation-row").removeClass("cm-operation-row")
			.css({ height: "", "min-height": "", "padding-top": "", "padding-bottom": "" });
		const filters = operation_filters(list);
		if (!filters.length || !list.data.length) return;
		const signature = JSON.stringify(filters);
		const column = () => $("<div>").addClass(`list-row-col hidden-xs ${marker}`)
			.css({ "min-width": "0", "flex": "1.5 1 0%", "overflow": "hidden" });
		column().text(__("Operation Progress"))
			.appendTo(list.$result.find(".list-header-subject"));
		const cells = new Map();
		list.$result.find(".list-row-container").each(function () {
			const row = $(this);
			row.find(".list-row").addClass("cm-operation-row")
				.css({ height: "auto", "min-height": "40px", "padding-top": "8px", "padding-bottom": "8px" });
			const name = row.find(".list-row-checkbox").attr("data-name");
			const cell = column().text(__("Loading…"))
				.appendTo(row.find(".list-row > .level-left"));
			cells.set(name, cell);
		});
		const current = () => list._cm_operation_generation === generation
			&& JSON.stringify(operation_filters(list)) === signature;
		frappe.call({
			method: "cardmasters_app.cardmasters_app.api.work_order_list.get_operation_progress",
			args: { names: list.data.map(doc => doc.name), filters },
			callback(response) {
				if (!current()) return;
				for (const [name, cell] of cells) {
					const rows = response.message?.[name] || [];
					cell.empty();
					if (!rows.length) cell.text(__("No matching operations"));
					for (const row of rows) {
						const repeated = rows.filter(other => other.operation === row.operation).length > 1;
						const operation = `${row.operation || __("Operation")}${repeated ? ` (#${row.idx})` : ""}`;
						const progress = __(row.progress || "Not set");
						const label = `${operation}: ${progress}`;
						// Only the operation name shrinks; keep its progress readable.
						$("<div>").css({ margin: "3px 0", "min-width": "0" }).html(
							`<span class="indicator-pill ${colors[row.progress] || "gray"}"
								style="max-width:100%;min-width:0;box-sizing:border-box;overflow:hidden"
								title="${escape(label)}" aria-label="${escape(label)}">
								<span style="min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escape(operation)}</span>
								<span style="flex-shrink:0;white-space:nowrap">:&nbsp;${escape(progress)}</span>
							</span>`
						).appendTo(cell);
					}
				}
			},
			error() {
				if (current()) for (const cell of cells.values()) cell.text(__("Progress unavailable"));
			},
		});
	};
})();
