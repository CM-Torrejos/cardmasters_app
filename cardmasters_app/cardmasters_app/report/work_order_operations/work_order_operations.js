frappe.query_reports["Work Order Operations"] = {
    filters: [
        { fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company",
            default: frappe.defaults.get_user_default("Company") },
        { fieldname: "work_order", label: __("Work Order"), fieldtype: "Link", options: "Work Order" },
        { fieldname: "branch_source", label: __("Branch Source"), fieldtype: "Select",
            options: [
                { value: "custom_for_branch", label: __("For Branch") },
                { value: "custom_production_branch", label: __("Production Branch") },
            ], default: "custom_for_branch" },
        { fieldname: "branch", label: __("Branch"), fieldtype: "Link", options: "Branch" },
        { fieldname: "operation", label: __("Operations"), fieldtype: "MultiSelectList",
            options: "Operation",
            get_data(txt) { return frappe.db.get_link_options("Operation", txt); } },
        { fieldname: "progress", label: __("Progress"), fieldtype: "MultiSelectList",
            get_data(txt) {
                return ["Not Started", "In Progress", "On Hold", "Done"]
                    .filter(value => __(value).toLowerCase().includes((txt || "").toLowerCase()))
                    .map(value => ({ value, description: __(value) }));
            } },
        { fieldname: "status", label: __("Work Order Status"), fieldtype: "Select",
            options: "\nDraft\nNot Started\nIn Process\nCompleted\nStopped\nClosed" },
    ],

    onload(report) {
        // Let several quick multi-select clicks settle before requesting the grid.
        const refresh = frappe.utils.debounce(() => {
            if (!report._no_refresh && report.report_name === "Work Order Operations") {
                report.refresh(true);
            }
        }, 350);
        report.filters.filter(filter => ["operation", "progress"].includes(filter.fieldname))
            .forEach(filter => {
                filter.on_change = () => {
                    if (!report._no_refresh) refresh();
                };
            });
    },

    formatter(value, row, column, data, default_formatter) {
        const formatted = default_formatter(value, row, column, data);
        if (!column.fieldname?.endsWith("_source_order")) return formatted;
        const label = data?.[column.fieldname.replace(/_source_order$/, "_source_label")];
        return label ? `${formatted} · ${frappe.utils.escape_html(label)}` : formatted;
    },

    get_datatable_options(options) {
        return Object.assign(options, {
            serialNoColumn: false, checkboxColumn: false,
            disableReorderColumn: true, inlineFilters: false,
        });
    },

    after_datatable_render(datatable) {
        // Keep the real grid (and its link formatting, resizing and export data).
        // The extra band lives inside the header, so native horizontal scrolling
        // moves both header levels together without a second scroll handler.
        datatable.cmOperationGroupsCleanup?.();
        const header = datatable.header;
        const band = document.createElement("div");
        band.className = "cm-operation-groups";
        band.style.cssText = "display:flex;order:-1;width:max-content";
        header.style.display = "flex";
        header.style.flexDirection = "column";
        header.appendChild(band);

        // Scope real borders to this grid, including virtualized rows and headers.
        // A shared rule keeps the upper band and group-ending columns identical.
        const separators = document.createElement("style");
        const columns = datatable.datamanager.getColumns();
        const scope = `.${datatable.style.scopeClass}`;
        const groupEnds = columns.flatMap((column, index) => {
            if (!column.operation_group ||
                column.operation_group === columns[index + 1]?.operation_group) return [];
            return [`${scope} .dt-cell--col-${column.colIndex}`];
        });
        separators.textContent = `
            ${scope} .dt-cell {
                border-right: 1px solid var(--border-color, #d1d8dd);
            }
            ${scope} .cm-operation-group {
                flex: none;
                box-sizing: border-box;
                padding: 8px;
                text-align: center;
                font-weight: 600;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                border-top: 1px solid var(--border-color, #d1d8dd);
                background: var(--subtle-fg, var(--fg-color, #f5f7fa));
            }
            ${scope} .cm-operation-group:first-child {
                border-left: 1px solid var(--border-color, #d1d8dd);
            }
            ${[`${scope} .cm-operation-group`, ...groupEnds].join(",")} {
                border-right: 2px solid var(--text-light, #98a2b3);
            }
        `;
        datatable.wrapper.appendChild(separators);

        let frame = null;
        let disposed = false;
        let groupCells = [];
        const sync = () => {
            frame = null;
            if (disposed) return;
            const columns = datatable.datamanager.getColumns();
            const cells = header.querySelectorAll(".dt-row-header > .dt-cell");
            const groups = [];
            cells.forEach((cell, index) => {
                const name = columns[index]?.operation_group || "";
                let group = groups[groups.length - 1];
                if (!group || group.name !== name) {
                    group = { name, width: 0 };
                    groups.push(group);
                }
                group.width += cell.getBoundingClientRect().width;
            });
            const structureChanged = groups.length !== groupCells.length ||
                groups.some((group, index) => group.name !== groupCells[index]?.name);
            if (structureChanged) {
                groupCells = groups.map(group => {
                    const cell = document.createElement("div");
                    cell.className = "cm-operation-group";
                    cell.textContent = group.name;
                    cell.title = group.name;
                    cell.style.width = `${group.width}px`;
                    return { name: group.name, width: group.width, cell };
                });
                band.replaceChildren(...groupCells.map(group => group.cell));
            } else {
                groups.forEach((group, index) => {
                    if (group.width !== groupCells[index].width) {
                        groupCells[index].cell.style.width = `${group.width}px`;
                        groupCells[index].width = group.width;
                    }
                });
            }
        };
        // The grid sets every column width during refresh. Measuring the entire
        // header after each write forces repeated browser layouts on wide reports.
        const scheduleSync = () => {
            if (!disposed && frame === null) frame = requestAnimationFrame(sync);
        };
        const observer = new ResizeObserver(scheduleSync);
        header.querySelectorAll(".dt-row-header > .dt-cell").forEach(cell => observer.observe(cell));
        // Schedule during drag too; observer delivery can lag behind pointer updates.
        const manager = datatable.columnmanager;
        const setHeaderWidth = manager.setColumnHeaderWidth;
        manager.setColumnHeaderWidth = function(...args) {
            const result = setHeaderWidth.apply(this, args);
            scheduleSync();
            return result;
        };
        scheduleSync();
        const cleanup = () => {
            disposed = true;
            if (frame !== null) cancelAnimationFrame(frame);
            observer.disconnect();
            manager.setColumnHeaderWidth = setHeaderWidth;
            band.remove();
            separators.remove();
        };
        datatable.cmOperationGroupsCleanup = cleanup;
        if (!datatable.cmOperationGroupsDestroyBound) {
            datatable.on("onDestroy", () => datatable.cmOperationGroupsCleanup?.());
            datatable.cmOperationGroupsDestroyBound = true;
        }
    },
};
