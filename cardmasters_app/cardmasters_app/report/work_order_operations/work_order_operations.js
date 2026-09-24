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
        { fieldname: "progress", label: __("Progress"), fieldtype: "Select",
            options: "\nNot Started\nIn Progress\nOn Hold\nDone" },
        { fieldname: "status", label: __("Work Order Status"), fieldtype: "Select",
            options: "\nDraft\nNot Started\nIn Process\nCompleted\nStopped\nClosed" },
    ],

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

        // Inset rules emphasize group boundaries without changing cell widths.
        // Column selectors also cover rows created later by grid virtualization.
        datatable.wrapper.classList.add("cm-operation-grid");
        const separators = document.createElement("style");
        const columns = datatable.datamanager.getColumns();
        separators.textContent = columns.flatMap((column, index) => {
            if (!column.operation_group ||
                column.operation_group === columns[index + 1]?.operation_group) return [];
            return [`.cm-operation-grid .dt-cell--col-${column.colIndex} {` +
                "box-shadow:inset -3px 0 0 var(--text-muted, #6c757d) !important;} "];
        }).join("\n");
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
                    cell.textContent = group.name;
                    cell.title = group.name;
                    cell.style.cssText = `flex:none;box-sizing:border-box;width:${group.width}px;` +
                        "padding:8px;text-align:center;font-weight:600;overflow:hidden;" +
                        "text-overflow:ellipsis;white-space:nowrap;border:1px solid var(--border-color);" +
                        "background:var(--subtle-fg,var(--fg-color));" +
                        "box-shadow:inset -3px 0 0 var(--text-muted, #6c757d)";
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
        // Update during the grid's drag handler as well as browser layout changes.
        // This override belongs only to this report's DataTable instance.
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
