frappe.ui.form.on('Credit Memo', {
    before_save: function(frm) {
        // Check if a sales order is actually linked
        if (frm.doc.sales_order) {
            // Fetch the custom_sponsored field value from the linked Sales Order
            frappe.db.get_value('Sales Order', frm.doc.sales_order, 'custom_sponsored')
                .then(r => {
                    // Check if the value exists and is not checked (0 or false)
                    if (r.message && !r.message.custom_sponsored) {
                        frappe.msgprint({
                            title: __('Notice'),
                            indicator: 'orange',
                            message: __('The linked Sales Order is not marked as Sponsored.')
                        });
                    }
                });
        }
    }
});