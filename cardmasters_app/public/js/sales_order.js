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