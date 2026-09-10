frappe.query_reports["Production Tower"] = {
    "filters": [ /* ... filters remain the same ... */ ],
    "treeView": true,
    "name_field": "label_name",
    "initial_depth": 3,
    "formatter": function(value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);

        const RED = "#d63939";
        const ORANGE = "#f76707";
        const YELLOW = "#f59f00";
        const GREEN = "#2fb344";
        const INFO_BLUE = "#1a73e8";

        // 1. Completion Rate Gradient
        if (column.fieldname == "completion_rate" && data.completion_rate) {
            let rate = parseFloat(data.completion_rate.replace('%', ''));
            let color;
            if (rate === 100) color = GREEN;
            else if (rate >= 75) color = YELLOW;
            else if (rate >= 40) color = ORANGE;
            else color = RED;
            
            value = `<span style="color: ${color}; font-weight: bold;">${value}</span>`;
        }

        // 2. Planning Health Warnings
        if (column.fieldname == "qty") {
            if (data.indent == 1) { 
                if (data.planning_status === "orphan") value = `<span style="color: ${RED}; font-weight: bold;">${value} (MISSING)</span>`;
                else if (data.planning_status === "shortfall") value = `<span style="color: ${ORANGE}; font-weight: bold;">${value} (PARTIAL)</span>`;
            } else if (data.indent == 0) { 
                if (data.incomplete_coverage) {
                    // Only this column stays RED for L0 alerts
                    value = `<span style="color: ${RED}; font-weight: bold;">${value} COVERED</span>`;
                } else if (data.completion_rate === "100%") {
                    value = `<span style="color: ${GREEN}; font-weight: bold;">${value}</span>`;
                }
            }
        }

        // 3. Labels and Icons (Neutral L0)
        if (column.fieldname == "label_name") {
            value = frappe.utils.escape_html(data.label_name || "");
            if (data.indent == 0) {
                if (data.is_orphan_so) {
                    value = `<strong style="color: ${INFO_BLUE}; font-size: 1.1em;">ℹ [SERVICE] ${value}</strong>`;
                } else if (data.completion_rate === "100%") {
                    value = `<strong style="color: ${GREEN}; font-size: 1.1em;">${value}</strong>`;
                } else {
                    // Bold but no Red distraction
                    value = `<strong>${value}</strong>`;
                }
            } else if (data.planning_status === "orphan") {
                value = `<span style="color: ${RED}; font-weight: bold;">⚠ ${value}</span>`;
            }

            // Keep document identity separate from the display label and sorting.
            // DataTable adds the expand/collapse control outside this link.
            if (["Sales Order", "Material Request", "Work Order"].includes(data.reference_doctype) && data.reference_name) {
                const href = frappe.utils.get_form_link(data.reference_doctype, data.reference_name);
                value = `<a href="${frappe.utils.escape_html(href)}" style="color: inherit; text-decoration: none;">${value}</a>`;
            }
        }

        return value;
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
        if (field === "completion_rate") return numeric(String(value ?? "").replace(/%$/, ""));
        if (field === "produced_qty" || field === "is_bypass") return numeric(value);
        // ISO dates compare chronologically; text uses natural ordering (WO-2 < WO-10).
        return value == null || String(value).trim() === "" ? null : String(value);
    }

    frappe.query_reports["Production Tower"].after_datatable_render = function(datatable) {
        const manager = datatable.datamanager;
        if (manager.productionTowerTreeSort) return;
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
    };
})();
