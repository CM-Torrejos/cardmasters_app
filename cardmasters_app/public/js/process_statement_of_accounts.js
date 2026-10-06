frappe.ui.form.on("Process Statement Of Accounts", {
    setup(frm) {
        frm.set_query("custom_soa_template", () => ({ filters: { enabled: 1, report_type: frm.doc.report } }));
    },
    refresh(frm) {
        if (!frm.is_new()) {
            frm.add_custom_button(__("Preview Template"), () => {
                if (frm.is_dirty()) {
                    frappe.msgprint(__("Save the statement before previewing its template."));
                    return;
                }
                cardmasters.preview_soa({ document_name: frm.doc.name, report_type: frm.doc.report });
            });
        }
        frm.add_custom_button(__("SOA Templates"), () => frappe.set_route("List", "SOA Template"));
    },
    report(frm) {
        frm.set_value("custom_soa_template", "");
    },
});
