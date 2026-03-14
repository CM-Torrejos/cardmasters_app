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
            if (data.indent == 0) {
                if (data.is_orphan_so) {
                    value = `<strong style="color: ${INFO_BLUE}; font-size: 1.1em;">ℹ [SERVICE] ${data.label_name}</strong>`;
                } else if (data.completion_rate === "100%") {
                    value = `<strong style="color: ${GREEN}; font-size: 1.1em;">${data.label_name}</strong>`;
                } else {
                    // Bold but no Red distraction
                    value = `<strong>${value}</strong>`;
                }
            } else if (data.planning_status === "orphan") {
                value = `<span style="color: ${RED}; font-weight: bold;">⚠ ${value}</span>`;
            }
        }

        return value;
    }
};