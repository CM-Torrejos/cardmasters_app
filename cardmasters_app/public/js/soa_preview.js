window.cardmasters = window.cardmasters || {};

cardmasters.preview_soa = function (options) {
    const dialog = new frappe.ui.Dialog({
        title: __("Preview Statement Template"),
        fields: [
            { fieldname: "document_name", fieldtype: "Link", options: "Process Statement Of Accounts",
                label: __("Saved Statement"), reqd: 1, default: options.document_name,
                get_query: () => ({ filters: options.report_type ? { report: options.report_type } : {} }) },
            { fieldname: "customer", fieldtype: "Link", options: "Customer", label: __("Customer"),
                description: __("Leave blank to preview the first customer on the statement.") },
            { fieldname: "output", fieldtype: "Select", label: __("Output"), options: "HTML Preview\nPDF", default: "HTML Preview" },
        ],
        primary_action_label: __("Preview"),
        primary_action(values) {
            const args = { ...values, template_name: options.template_name,
                template_document: options.template_document ? JSON.stringify(options.template_document) : undefined };
            delete args.output;
            Object.keys(args).forEach((key) => { if (args[key] === undefined) delete args[key]; });
            if (values.output === "PDF") {
                open_url_post("/api/method/cardmasters_app.cardmasters_app.services.soa_templates.preview",
                    { ...args, as_pdf: 1 }, true);
                return;
            }
            frappe.call({
                method: "cardmasters_app.cardmasters_app.services.soa_templates.preview",
                args, freeze: true, freeze_message: __("Generating preview…"),
                callback(r) {
                    if (!r.message) return;
                    const preview = new frappe.ui.Dialog({ title: __("Statement Preview"), size: "extra-large",
                        fields: [{ fieldname: "preview", fieldtype: "HTML" }] });
                    const frame = document.createElement("iframe");
                    frame.setAttribute("sandbox", "");
                    frame.title = __("Statement Preview");
                    frame.style.cssText = "width:100%;height:70vh;border:0;background:white";
                    frame.srcdoc = r.message;
                    preview.fields_dict.preview.$wrapper.empty().append(frame);
                    preview.show();
                },
            });
        },
    });
    dialog.show();
};
