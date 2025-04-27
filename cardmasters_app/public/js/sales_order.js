// Create Petty Cash Request
frappe.ui.form.on('Sales Order', {
	refresh(frm) {
    	if (!frm.is_new()) {
        	frm.add_custom_button('Petty Cash Request', () => {
            	frappe.new_doc('Petty Cash Request', {
                	sales_order: frm.doc.name
            	});
        	}, 'Create'); // This adds it under the 'Create' dropdown
    	}
	}
});

// Create Artist Sheet
frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
    	if (!frm.doc.__islocal) {
        	// Add the button to the "Create" dropdown
        	frm.add_custom_button(__('Create Artist Sheet'), function() {
            	frappe.new_doc('Artist Sheet', {
                	sales_order: frm.doc.name,
                	artist: frm.doc.custom_artist
            	});
        	}, __('Create')); // The third parameter places it in the "Create" dropdown
    	}
	}
});
