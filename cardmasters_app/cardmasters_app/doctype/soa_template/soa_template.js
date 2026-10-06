frappe.ui.form.on("SOA Template", {
    refresh(frm) {
        frm.add_custom_button(__("Preview"), () => {
            cardmasters.preview_soa({ report_type: frm.doc.report_type,
                template_document: { name: frm.is_new() ? undefined : frm.doc.name,
                    report_type: frm.doc.report_type, html: frm.doc.html, css: frm.doc.css } });
        });
    },
});
