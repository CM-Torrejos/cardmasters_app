frappe.ui.form.on('Credit Memo', {
    validate: function(frm) {
        if (frm.doc.sales_order) {
            
            // 1. Return an explicit Promise so Frappe halts the save sequence
            return new Promise((resolve, reject) => {
                
                frappe.db.get_value('Sales Order', frm.doc.sales_order, 'custom_sponsored')
                    .then(r => {
                        // Check if the value exists and is 0/false
                        if (r.message && !r.message.custom_sponsored) {
                            
                            // 2. Explicitly flag the form as invalid
                            frappe.validated = false;
                            
                            // 3. Use a 50ms timeout to bypass the DOM freeze collision
                            setTimeout(() => {
                                frappe.msgprint({
                                    title: __('Notice'),
                                    indicator: 'orange',
                                    message: __('The linked Sales Order is not marked as Sponsored')
                                });
                            }, 50);
                            
                            // 4. Reject the promise to completely abort the save
                            reject(); 
                            
                        } else {
                            // If it IS sponsored, resolve the promise and let it save
                            resolve(); 
                        }
                    });
            });
        }
    }
});