frappe.ui.form.on("Process Statement Of Accounts", {
    setup(frm) {
        frm.set_query("custom_soa_template", () => ({ filters: { enabled: 1, report_type: frm.doc.report } }));
    },
    refresh(frm) {
        if (!frm.is_new()) {
            [["CSV", "csv", "data"], ["Excel", "xlsx", "template"], ["Excel (Data Table)", "xlsx", "data"]].forEach(([label, format, layout]) => {
                frm.add_custom_button(__(label), () => {
                    if (frm.is_dirty()) {
                        frappe.msgprint(__("Save the statement before exporting."));
                        return;
                    }
                    const dialog = new frappe.ui.Dialog({
                        title: __("Export Statement"),
                        fields: [{ fieldname: "customer", fieldtype: "Link", options: "Customer",
                            label: __("Customer"),
                            description: __("Leave blank to export all customers on this statement."),
                            get_query: () => ({ filters: { name: ["in", (frm.doc.customers || []).map(row => row.customer)] } }) }],
                        primary_action_label: __("Download {0}", [label]),
                        primary_action(values) {
                            open_url_post("/api/method/cardmasters_app.cardmasters_app.services.soa_exports.download_export", {
                                document_name: frm.doc.name, file_format: format, layout, customer: values.customer || "",
                            }, true);
                            dialog.hide();
                        },
                    });
                    dialog.show();
                }, __("Export"));
            });
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
