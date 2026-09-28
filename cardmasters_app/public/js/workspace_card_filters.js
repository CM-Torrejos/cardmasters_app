// Extend the card dialog and registered widget without modifying Frappe assets.
(() => {
	const fieldname = "custom_card_filters";
	const show_count = "custom_card_show_count";
	const count_color = "custom_card_count_color";
	const colors = ["Grey", "Green", "Red", "Orange", "Pink", "Yellow", "Blue", "Cyan"];

	function edit_filters(card_dialog) {
		const rows = card_dialog.fields_dict.links.grid.get_data();
		const choices = rows.map((row, index) => ({ row, index })).filter(({ row }) =>
			row.link_type === "DocType" && row.link_to &&
			!frappe.boot.single_types.includes(row.link_to)
		);
		if (!choices.length) {
			frappe.msgprint(__("Add a DocType list link to this card first."));
			return;
		}
		const pending = new Map();
		let current, group, dialog, generation = 0;
		const capture = () => {
			if (current && group) pending.set(current.index, {
				[fieldname]: JSON.stringify(group.get_filters()),
				[show_count]: Number(dialog.get_value(show_count)) ? 1 : 0,
				[count_color]: dialog.get_value(count_color) || "Grey",
			});
		};
		dialog = new frappe.ui.Dialog({
			title: __("Card Link Filters and Count"),
			size: "large",
			fields: [
				{
					fieldname: "card_link", fieldtype: "Select", label: __("Card Link"),
					options: choices.map(({ row, index }) => ({
						value: String(index), label: `${index + 1}. ${row.label || row.link_to}`,
					})),
					onchange: () => load_filters(),
				},
				{ fieldname: "filter_area", fieldtype: "HTML" },
				{ fieldname: "count_section", fieldtype: "Section Break", label: __("Result Count") },
				{ fieldname: show_count, fieldtype: "Check", label: __("Show Result Count"),
					description: __("Count records matching this link's filters.") },
				{ fieldname: count_color, fieldtype: "Select", label: __("Count Color"),
					options: colors, default: "Grey", depends_on: `eval:doc.${show_count}` },
			],
			primary_action_label: __("Apply"),
			primary_action: () => {
				if (!group) return;
				capture();
				for (const { row, index } of choices) {
					if (pending.has(index)) Object.assign(row, pending.get(index));
				}
				card_dialog.fields_dict.links.grid.refresh();
				dialog.hide();
			},
		});
		async function load_filters() {
			if (!dialog) return;
			capture();
			group = null;
			const ticket = ++generation;
			current = choices.find(({ index }) => String(index) === dialog.get_value("card_link"));
			if (!current) return;
			const { row, index } = current;
			const settings = pending.get(index) || row;
			dialog.set_value(show_count, Number(settings[show_count]) ? 1 : 0);
			dialog.set_value(count_color, settings[count_color] || "Grey");
			const parent = dialog.get_field("filter_area").$wrapper.empty();
			await frappe.model.with_doctype(row.link_to);
			if (ticket !== generation) return;
			const next_group = new frappe.ui.FilterGroup({ parent, doctype: row.link_to, on_change: () => {} });
			const saved = settings[fieldname] || "[]";
			const filters = frappe.utils.get_filter_from_json(saved, row.link_to);
			// add_filters() updates a popover button which inline groups do not have.
			// Load individual filters and wait for their controls before enabling Apply.
			next_group.toggle_empty_filters(!filters.length);
			for (const filter of filters) {
				await next_group.add_filter(...filter);
			}
			if (ticket === generation) group = next_group;
		}
		dialog.show();
		dialog.set_value("card_link", String(choices[0].index));
		if (!current) load_filters();
	}

	const make = frappe.ui.Dialog.prototype.make;
	frappe.ui.Dialog.prototype.make = function () {
		// Card dialogs are created through several private constructors in Frappe.
		// Identify their table schema rather than translated titles or DOM labels.
		const table = this.fields?.find((df) => df.fieldname === "links" && df.fieldtype === "Table");
		if (table?.fields?.some((df) => df.fieldname === "link_type") &&
			!table.fields.some((df) => df.fieldname === fieldname)) {
			table.fields.push({ fieldname, fieldtype: "Code", hidden: 1 });
			table.fields.push({ fieldname: show_count, fieldtype: "Check", hidden: 1 });
			table.fields.push({ fieldname: count_color, fieldtype: "Data", hidden: 1 });
			for (const name of ["link_type", "link_to"]) {
				const df = table.fields.find((field) => field.fieldname === name);
				const original = df.onchange;
				df.onchange = function (...args) {
					this.doc[fieldname] = "[]";
					return original?.apply(this, args);
				};
			}
			this.fields.push({
				fieldname: "edit_card_link_filters", fieldtype: "Button",
				label: __("Edit Link Filters"), click: () => edit_filters(this),
			});
		}
		return make.apply(this, arguments);
	};

	const LinksWidget = frappe.widget.widget_factory.links;
	frappe.widget.widget_factory.links = class extends LinksWidget {
		set_body() {
			super.set_body();
			this.links.forEach((item, index) => {
				if (item.link_type !== "DocType" ||
					frappe.boot.single_types.includes(item.link_to) ||
					this.link_list[index].hasClass("disabled-link")) return;
				try {
					const filters = frappe.utils.process_filter_expression(item[fieldname] || "[]");
					if (!Array.isArray(filters)) return;
					const link = this.link_list[index];
					if (Number(item[show_count]) && !this.in_customize_mode) {
						this.set_result_count(item, link, filters);
					}
					if (!filters.length) return;
					const route = frappe.utils.generate_route({
						name: item.link_to, type: "DocType", doc_view: "List",
					});
					const url = new URL(route, window.location.origin);
					for (const [doctype, field, operator, value] of filters) {
						const key = doctype && !field.includes(".") ? `${doctype}.${field}` : field;
						// Repeated parameters retain multiple conditions on the same field.
						url.searchParams.append(key, JSON.stringify([operator, value]));
					}
					link.attr("href", url.pathname + url.search + url.hash);
				} catch (error) {
					console.error("Invalid workspace card filters", item.link_to, error);
				}
			});
		}

		async set_result_count(item, link, filters) {
			try {
				// Use the same permission-aware count API as native shortcuts.
				const count = await frappe.db.count(item.link_to, { filters });
				const chosen = colors.includes(item[count_color]) ? item[count_color] : "Grey";
				const color = count ? chosen.toLowerCase() : "gray";
				$("<span>")
					.addClass(`indicator-pill no-indicator-dot ellipsis ${color}`)
					.css({ "flex-shrink": 0, "margin-left": "8px" })
					.text(count)
					.attr("title", __("Matching records"))
					.appendTo(link);
			} catch (error) {
				// A failed count must not prevent navigation or display a misleading zero.
				console.warn("Unable to count workspace card link", item.link_to, error);
			}
		}
	};
})();
