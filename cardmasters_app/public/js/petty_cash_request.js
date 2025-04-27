// TODO:Cleanup script
// TODO:Hook to workflows
// Create buttons
frappe.ui.form.on('Petty Cash Request', {
	refresh: function(frm) {
    	// Clear existing custom buttons under 'Create'
    	frm.clear_custom_buttons('Create');

    	// Check for linked Petty Cash Voucher
    	frappe.call({
        	method: "frappe.client.get_list",
        	args: {
            	doctype: "Petty Cash Voucher",
            	filters: {
                	petty_cash_request: frm.doc.name
            	},
            	limit_page_length: 1
        	},
        	callback: function(response) {
            	if (response.message.length == 0) {
                	// If linked Petty Cash Voucher exists, show only that button
                	frm.add_custom_button(__('Petty Cash Voucher'), function() {
                    	frappe.new_doc('Petty Cash Voucher', {
                        	'petty_cash_request': frm.doc.name
                    	});
                	}, 'Create');
            	} else {
                	// Otherwise, show Purchase Invoice and Purchase Receipt buttons
                	frm.add_custom_button(__('Purchase Invoice'), function() {
                    	frappe.new_doc('Purchase Invoice', {
                        	'petty_cash_request': frm.doc.name
                    	});
                	}, 'Create');

                	frm.add_custom_button(__('Purchase Receipt'), function() {
                    	frappe.new_doc('Purchase Receipt', {
                        	'petty_cash_request': frm.doc.name
                    	});
                	}, 'Create');
            	}
        	}
    	});
	}
});

