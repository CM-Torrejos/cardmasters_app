frappe.ui.form.on("SOA Template", {
    refresh(frm) {
        frm.add_custom_button(__("Preview"), () => {
            cardmasters.preview_soa({ report_type: frm.doc.report_type,
                template_document: { name: frm.is_new() ? undefined : frm.doc.name,
                    ...Object.fromEntries(["report_type", "html", "css", "data_source", "excel_layout", "contact_phone", "contact_email",
                        "bank_name", "bank_account", "bank_payee", "payment_reminder", "prepared_by", "prepared_title",
                        "checked_by", "checked_title"].map(field => [field, frm.doc[field]])) } });
        });
    },
});
