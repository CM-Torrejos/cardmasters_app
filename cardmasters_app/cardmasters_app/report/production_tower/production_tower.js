frappe.query_reports["Production Tower"] = {
    "filters": [
        {
            fieldname: "company",
            label: __("Company"),
            fieldtype: "Link",
            options: "Company"
        },
        {
            fieldname: "target_date",
            label: __("Target Date"),
            fieldtype: "Date"
        },
        {
            fieldname: "branch_source",
            label: __("Branch Source"),
            fieldtype: "Select",
            options: [
                { value: "branch", label: __("Sales Order Branch") },
                { value: "custom_production_branch", label: __("Production Branch") }
            ],
            default: "branch"
        },
        {
            fieldname: "branch",
            label: __("Branch"),
            fieldtype: "Link",
            options: "Branch"
        },
        {
            fieldname: "hide_completed",
            label: __("Hide 100% Completed"),
            fieldtype: "Check",
            default: 0
        }
    ],
    "treeView": true,
    "name_field": "label_name",
    "initial_depth": 0,
    get_datatable_options(options) {
        return Object.assign(options, { serialNoColumn: false, checkboxColumn: false, cellHeight: 40 });
    },
    formatter(value, row, column, data, default_formatter) {
        if (!data) return default_formatter(value, row, column, data);
        const escape = value => frappe.utils.escape_html(String(value ?? ""));
        const secondary = label => ` <span class="pt-secondary">${escape(label)}</span>`;
        const field = column.fieldname;

        if (["custom_blue_order", "custom_rush_order"].includes(field)) {
            if (value == null) return "";
            const blue = field === "custom_blue_order";
            return Number(value) ? `<span class="pt-badge pt-${blue ? "blue" : "rush"}">${escape(__(blue ? "Blue" : "Rush"))}</span>`
                : `<span class="pt-muted" title="${escape(__(blue ? "Not a blue order" : "Not a rush order"))}">—</span>`;
        }
        if (field === "label_name") {
            const types = { "Sales Order": "SO", "Material Request": "MR", "Delivery Note": "SR", "Work Order": "WO" };
            const kind = data.row_type === "operation" ? __("Op") : types[data.reference_doctype] || __("Item");
            let label = `<span class="pt-kind">${escape(kind)}</span> <span class="${data.indent === 0 ? "pt-source" : "pt-label"}" title="${escape(data.label_name)}">${escape(data.label_name)}</span>`;
            if (data.is_orphan_so) label += secondary(__("Service"));
            if (types[data.reference_doctype] && data.reference_name) {
                const href = frappe.utils.get_form_link(data.reference_doctype, data.reference_name);
                label = `<a class="pt-reference" href="${escape(href)}" title="${escape(data.label_name)}">${label}</a>`;
            }
            return label;
        }
        if (field === "completion_rate" && data.row_type === "operation") {
            const tone = { "Not Started": "neutral", "In Progress": "blue", "On Hold": "warning", "Done": "done" }[value] || "neutral";
            return value ? `<span class="pt-badge pt-${tone}">${escape(__(value))}</span>` : "";
        }
        if (field === "completion_rate" && value) {
            const rate = Math.max(0, Math.min(100, parseFloat(value) || 0));
            const pending = String(value).includes(`(${__("Pending Posting")})`);
            return `<span class="pt-completion" title="${escape(value)}"><span class="pt-meter" aria-hidden="true"><span class="${rate === 100 ? "pt-meter-done" : ""}" style="width:${rate}%"></span></span><span>${rate}%</span></span>`
                + (pending ? secondary(__("Pending posting")) : "");
        }

        const formatted = default_formatter(value, row, column, data);
        if (field === "qty") {
            let hint = "";
            if (data.indent === 1 && data.planning_status === "orphan") hint = __("No work order");
            else if ((data.indent === 1 && data.planning_status === "shortfall") ||
                (data.indent === 0 && data.incomplete_coverage)) hint = __("Pending");
            else if (data.indent === 2 && data.has_no_operations) hint = __("No operations");
            return `<span class="pt-quantity">${formatted}</span>`
                + (hint ? ` <span class="pt-attention">${escape(hint)}</span>` : "");
        }
        if (field === "custom_quick_production_note" && value) {
            return `<span title="${escape(value)}">${formatted}</span>`;
        }
        return formatted;
    },

    setup_presentation(datatable) {
        // The tree/sort tests also use this hook without a browser DOM.
        if (!datatable.wrapper) return;
        datatable.productionTowerPresentationCleanup?.();
        const scope = `.${datatable.style.scopeClass}`;
        const style = document.createElement("style");
        style.textContent = `
            ${scope} .pt-kind { display:inline-block; min-width:28px; font-size:10px; letter-spacing:.03em; color:var(--text-muted); font-weight:600; }
            ${scope} .pt-source { font-weight:600; }
            ${scope} .pt-reference { color:var(--text-color); text-decoration:none; }
            ${scope} .pt-reference:hover { text-decoration:underline; }
            ${scope} .pt-secondary, ${scope} .pt-muted { color:var(--text-muted); font-size:11px; }
            ${scope} .pt-attention { color:var(--text-on-orange, #b45309); font-size:11px; margin-left:4px; }
            ${scope} .pt-quantity { font-variant-numeric:tabular-nums; }
            ${scope} .pt-badge { display:inline-block; border-radius:4px; padding:2px 6px; line-height:18px; font-size:11px; font-weight:500; }
            ${scope} .pt-neutral { background:var(--control-bg); color:var(--text-muted); }
            ${scope} .pt-blue { background:var(--bg-blue, #eff6ff); color:var(--text-on-blue, #1d4ed8); }
            ${scope} .pt-rush, ${scope} .pt-warning { background:var(--bg-orange, #fff7ed); color:var(--text-on-orange, #9a3412); }
            ${scope} .pt-done { background:var(--bg-green, #f0fdf4); color:var(--text-on-green, #15803d); }
            ${scope} .pt-completion { display:inline-flex; align-items:center; gap:7px; font-variant-numeric:tabular-nums; }
            ${scope} .pt-meter { display:inline-block; width:44px; height:4px; overflow:hidden; border-radius:3px; background:var(--border-color); }
            ${scope} .pt-meter > span { display:block; height:100%; background:var(--blue-400, #60a5fa); }
            ${scope} .pt-meter > .pt-meter-done { background:var(--green-500, #22c55e); }
            ${scope} .dt-row:has(.pt-source) .dt-cell { background-color:var(--subtle-fg); }
            ${scope} .dt-cell__content { line-height:24px; }
        `;
        datatable.wrapper.appendChild(style);

        const toolbar = document.createElement("div");
        toolbar.className = "pt-toolbar";
        toolbar.style.cssText = "display:flex;flex-wrap:wrap;align-items:center;justify-content:space-between;gap:10px;padding:12px 0;";
        const levels = document.createElement("div");
        levels.className = "btn-group";
        levels.setAttribute("role", "group");
        levels.setAttribute("aria-label", __("Show detail level"));
        const buttons = [];
        const select = depth => {
            datatable.productionTowerDepth = depth;
            buttons.forEach((button, index) => {
                button.classList.toggle("btn-primary", index === depth);
                button.classList.toggle("btn-default", index !== depth);
                button.setAttribute("aria-pressed", String(index === depth));
            });
            datatable.rowmanager.setTreeDepth(depth);
        };
        [__("Orders"), __("Items"), __("Work Orders"), __("All details")].forEach((label, depth) => {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "btn btn-sm";
            button.textContent = label;
            button.title = depth === 3 ? __("Show every level, including all rows for export") : label;
            button.onclick = () => select(depth);
            levels.appendChild(button);
            buttons.push(button);
        });
        const counts = { "Sales Order": 0, "Material Request": 0, "Delivery Note": 0 };
        datatable.datamanager.data.forEach(row => {
            if (row.indent === 0 && row.reference_doctype in counts) counts[row.reference_doctype]++;
        });
        const summary = document.createElement("span");
        summary.className = "text-muted small";
        summary.textContent = [
            [counts["Sales Order"], __("Sales Orders")],
            [counts["Material Request"], __("Material Requests")],
            [counts["Delivery Note"], __("Sales Returns")],
        ].map(([count, label]) => `${count} ${label}`).join(" · ");
        toolbar.append(levels, summary);
        datatable.wrapper.insertBefore(toolbar, datatable.datatableWrapper);
        // Restore the chosen level after changing report filters; no server call.
        select(datatable.productionTowerDepth ?? 0);
        datatable.productionTowerPresentationCleanup = () => { toolbar.remove(); style.remove(); };
        if (!datatable.productionTowerPresentationDestroyBound) {
            datatable.on("onDestroy", () => datatable.productionTowerPresentationCleanup?.());
            datatable.productionTowerPresentationDestroyBound = true;
        }
    }
};
// Sorting is local to this report. Keep DataTable's row identities intact: its
// formatter, selection, tree controls and print output all use original indices.
(() => {
    const collator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });
    const numeric = value => {
        if (value == null || String(value).trim() === "") return null;
        const number = Number(value);
        return Number.isFinite(number) ? number : null;
    };

    function sortValue(data, field, rowIndex) {
        const value = data[field];
        if (field === "_rowIndex") return rowIndex;
        if (field === "qty") {
            // SO/MR: proportion of items fully planned. Item: planned / ordered.
            // WO: actual planned quantity. Never compare across these levels.
            if (Object.prototype.hasOwnProperty.call(data, "_sort_qty")) {
                return numeric(data._sort_qty);
            }
            // Also support older prepared report results without the raw key.
            if (typeof value === "string" && value.includes("/")) {
                const [planned, required] = value.split("/").map(numeric);
                return planned !== null && required > 0 ? planned / required : null;
            }
            return numeric(value);
        }
        if (field === "completion_rate") {
            if (data.row_type === "operation") {
                return ({ "Not Started": 0, "In Progress": 1, "On Hold": 2, "Done": 3 })[value] ?? null;
            }
            return numeric(String(value ?? "").split("%")[0]);
        }
        if (["produced_qty", "custom_blue_order", "custom_rush_order"].includes(field)) return numeric(value);
        // ISO dates compare chronologically; text uses natural ordering (WO-2 < WO-10).
        return value == null || String(value).trim() === "" ? null : String(value);
    }

    frappe.query_reports["Production Tower"].after_datatable_render = function(datatable) {
        const manager = datatable.datamanager;
        if (manager.productionTowerTreeSort) {
            frappe.query_reports["Production Tower"].setup_presentation(datatable);
            return;
        }
        manager.productionTowerTreeSort = true;

        let sourceRows, roots, nodes;
        let pendingVisibleRows = null;
        function tree() {
            if (sourceRows === manager.rows) return;
            sourceRows = manager.rows;
            roots = [];
            nodes = new Map();
            pendingVisibleRows = null;
            const stack = [];
            for (const row of sourceRows) {
                const node = { index: row.meta.rowIndex, indent: row.meta.indent, children: [] };
                while (stack.length && stack[stack.length - 1].indent >= node.indent) stack.pop();
                node.parent = stack[stack.length - 1];
                (node.parent ? node.parent.children : roots).push(node);
                nodes.set(node.index, node);
                stack.push(node);
            }
        }

        // DataTable's async sortRows still updates the header and invokes the
        // usual render/events. Replace only the flat ordering operation.
        manager._sortRows = function(colIndex, direction) {
            tree();
            pendingVisibleRows = new Set(datatable.bodyRenderer.visibleRowIndices);
            const column = this.getColumn(colIndex);
            const field = column.fieldname || column.id;
            const keys = new Map(Array.from(nodes.keys(), index =>
                [index, sortValue(this.data[index], field, index)]));
            const compare = (a, b) => {
                if (direction === "none") return a.index - b.index;
                const left = keys.get(a.index), right = keys.get(b.index);
                // Missing/inapplicable values stay last in both directions.
                if (left === null || right === null) {
                    if (left !== right) return left === null ? 1 : -1;
                    return a.index - b.index;
                }
                const result = typeof left === "number" && typeof right === "number"
                    ? left - right : collator.compare(String(left), String(right));
                // Ties always use original order, independent of previous clicks.
                return result ? result * (direction === "desc" ? -1 : 1) : a.index - b.index;
            };
            const order = [];
            function visit(siblings) {
                for (const node of siblings.slice().sort(compare)) {
                    order.push(node.index);
                    visit(node.children);
                }
            }
            visit(roots);
            this.rowViewOrder = order;
            if (this.hasColumnById("_rowIndex")) {
                const serialColumn = this.getColumnIndexById("_rowIndex");
                order.forEach((index, position) => {
                    const cell = this.getCell(serialColumn, index);
                    cell.content = String(position + 1);
                    delete cell.html;
                });
            }
        };

        // Use explicit branch membership. The upstream indent scan can run past
        // the end of an item's branch when it encounters a shallower ancestor.
        manager.getChildren = function(index) {
            tree();
            const result = [];
            function visit(node) {
                for (const child of node.children) {
                    result.push(child.index);
                    visit(child);
                }
            }
            const node = nodes.get(Number(index));
            if (node) visit(node);
            return result;
        };
        manager.getImmediateChildren = function(index) {
            tree();
            return (nodes.get(Number(index))?.children || []).map(node => node.index);
        };

        const renderer = datatable.bodyRenderer;
        const renderRows = renderer.renderRows;
        renderer.renderRows = function(rows) {
            tree();
            const requested = new Set(rows.map(row => row.meta.rowIndex));
            const visibleBeforeSort = pendingVisibleRows;
            pendingVisibleRows = null;
            const visible = [];
            const hidden = new Set();
            // View order is preorder, so the parent's visibility is known first.
            for (const index of manager.rowViewOrder) {
                const node = nodes.get(index);
                if (node.parent && (hidden.has(node.parent.index)
                    || manager.getRow(node.parent.index).meta.isTreeNodeClose)) {
                    hidden.add(index);
                    continue;
                }
                if (requested.has(index) && (!visibleBeforeSort || visibleBeforeSort.has(index))) {
                    visible.push(manager.getRow(index));
                }
            }
            // Preserve collapsed/filtered rows during sorting. Keep visibleRows
            // ordered too, so CSV export agrees with the table after expanding.
            return renderRows.call(this, visible);
        };
        frappe.query_reports["Production Tower"].setup_presentation(datatable);
    };
})();
