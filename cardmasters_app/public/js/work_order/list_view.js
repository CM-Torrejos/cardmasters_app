frappe.ui.form.on('Work Order', {
    refresh: function(frm) {
        // 1. Add the "Complete Job" button to the top bar
        frm.add_custom_button(__('Complete Job'), function() {
            
            // Build the checklist fields
            let job_fields = frm.doc.custom_cm_jobs.map(row => {
                return {
                    label: row.job,
                    fieldname: row.name,
                    fieldtype: 'Check',
                    default: row.custom_is_complete
                };
            });

            if (job_fields.length === 0) {
                frappe.msgprint(__('No jobs found in the Operations table.'));
                return;
            }

            // 2. Open the Modal
            let d = new frappe.ui.Dialog({
                title: __('Complete Jobs'),
                fields: job_fields,
                primary_action_label: __('Update'), // This is the button you want
                primary_action(values) {
                    // 3. Update the child table values
                    let updates = Object.keys(values).map(row_id => {
                        return frappe.model.set_value('CM Jobs', row_id, 'custom_is_complete', values[row_id]);
                    });

                    Promise.all(updates).then(() => {
                        // 4. Submit the document
                        // Using 'Submit' instead of 'Save' as requested
                        frm.page.set_indicator('Submitting...', 'orange');
                        
                        frm.save('Submit').then(() => {
                            d.hide();
                            frappe.show_alert({
                                message: __('Work Order Submitted Successfully'), 
                                indicator: 'green'
                            });
                        }).catch(err => {
                            // If submission fails (usually due to missing fields)
                            console.error(err);
                        });
                    });
                }
            });

            d.show();
        }).addClass('btn-primary');
    }
});

// 

frappe.listview_settings['Work Order'] = {
    refresh: function(listview) {
        // Add a button to the List Actions
        listview.page.add_inner_button(__('Complete Job'), function() {
            
            // 1. Get the selected Work Orders from the list checkboxes
            let selected_docs = listview.get_checked_items();

            if (selected_docs.length === 0) {
                frappe.msgprint(__('Please select at least one Work Order first.'));
                return;
            }

            // If only one is selected, we can show its specific jobs
            if (selected_docs.length === 1) {
                let docname = selected_docs[0].name;
                
                // Fetch the full document to get the child table rows
                frappe.db.get_doc('Work Order', docname).then(doc => {
                    let job_fields = doc.custom_cm_jobs.map(row => {
                        return {
                            label: row.job,
                            fieldname: row.name,
                            fieldtype: 'Check',
                            default: row.custom_is_complete
                        };
                    });

                    let d = new frappe.ui.Dialog({
                        title: __(`Complete Jobs for ${docname}`),
                        fields: job_fields,
                        primary_action_label: __('Update'),
                        primary_action(values) {
                            // Update the rows
                            Object.keys(values).forEach(row_id => {
                                frappe.model.set_value('CM Jobs', row_id, 'custom_is_complete', values[row_id]);
                            });

                            // Save and Submit the doc
                            frappe.call({
                                method: 'frappe.desk.form.save.savedocs',
                                args: { doc: doc, action: 'Submit' },
                                callback: function(r) {
                                    if (!r.exc) {
                                        d.hide();
                                        listview.refresh();
                                        frappe.show_alert(__('Work Order Submitted'), 'green');
                                    }
                                }
                            });
                        }
                    });
                    d.show();
                });
            } else {
                frappe.msgprint(__('Bulk update via list is limited to 1 Work Order at a time for job-specific checks.'));
            }
        }).addClass('btn-primary');
    }
};