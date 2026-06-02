frappe.ui.form.on('Payment Entry', {
    setup: function(frm) {
        // Register realtime listener ONCE in setup (not refresh) to prevent accumulation.
        // If registered in refresh, a new listener stacks on every form refresh.
        frappe.realtime.on("reversal_cleared", function(data) {
            // Only reload if the broadcast is talking about THIS specific record
            if (data.docname === frm.doc.name) {
                frm.reload_doc();
            }
        });
    },

    refresh: function(frm) {
        // Only show button if submitted AND NOT reversed AND user has the Accounts Manager role
        if (frm.doc.docstatus === 1 && !frm.doc.custom_is_reversed) {
            
            frm.add_custom_button(__('Reverse Out-of-Period'), function() {
                
                // Prevent action if there are unsaved changes on the form
                if (frm.is_dirty()) {
                    frappe.msgprint({
                        title: __('Unsaved Changes'),
                        indicator: 'orange',
                        message: __('Please save or discard any changes on this Payment Entry before reversing.')
                    });
                    return;
                }
                
                // Launch the Date Selection Prompt
                frappe.prompt([
                    {
                        label: __('Reversal Posting Date'),
                        fieldname: 'reversal_date',
                        fieldtype: 'Date',
                        reqd: 1, // Mandatory
                        default: frappe.datetime.get_today(),
                        description: __('Select the open period date for the Reversal Journal Entry.')
                    }
                ], function(values) {
                    
                    // Action triggered when the user clicks 'Submit' on the prompt
                    frappe.call({
                        method: 'cardmasters_app.cardmasters_app.api.payment_entry.reverse_payment_entry', 
                        args: {
                            payment_entry_name: frm.doc.name,
                            reversal_date: values.reversal_date 
                        },
                        freeze: true,
                        freeze_message: __('Generating Out-of-Period Reversal...'),
                        callback: function(r) {
                            if (r.message) {
                                frappe.msgprint({
                                    title: __('Success'),
                                    indicator: 'green',
                                    message: __('Payment successfully reversed. Journal Entry created: <b>{0}</b>', [r.message])
                                });
                                // Refreshes the screen to fetch the new database timestamp and hide the button
                                frm.reload_doc(); 
                            }
                        }
                    });
                }, __('Select Reversal Date'), __('Reverse Payment')); 

            }, __('Actions')); // Places the button inside the 'Actions' dropdown
        }
    }
});