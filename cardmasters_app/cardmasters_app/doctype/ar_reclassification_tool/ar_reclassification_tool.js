// Copyright (c) 2026, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.ui.form.on("AR Reclassification Tool", {
	refresh(frm) {

	},

    reclassify_to_employee(frm) {
        frappe.confirm(
            __('Are you sure you want to run batch reclassification? An Excel-compatible audit spreadsheet log will be generated automatically at the end.'), 
            function() {
                
                let current_filters = {
                    company: frm.doc.company,
                    report_date: frm.doc.posting_date,
                    range: frm.doc.range
                };

                frappe.show_progress(__("Processing Reclassification"), 0, 100, __("Querying core Accounts Receivable report context..."));

                frappe.realtime.on("reclass_progress", function(data) {
                    frappe.show_progress(__("Processing Reclassification"), data.current, data.total, data.message);
                });

                frappe.call({
                    method: "cardmasters_app.cardmasters_app.doctype.ar_reclassification_tool.ar_reclassification_tool.run_employee_ar_reclassification",
                    args: {
                        filters: current_filters
                    },
                    callback: function(r) {
                        if (!r.exc && r.message) {
                            frappe.msgprint({
                                title: __('Reclassification Run Complete'),
                                indicator: r.message.status === 'complete' ? 'green' : 'orange',
                                message: r.message.message
                            });

                            if (r.message.file_url) {
                                window.open(r.message.file_url, '_blank');
                            }
                            frm.refresh();
                        }
                    },
                    always: function() {
                        frappe.realtime.off("reclass_progress");
                        frappe.hide_progress();
                    }
                });
            }
        );
    }
});
