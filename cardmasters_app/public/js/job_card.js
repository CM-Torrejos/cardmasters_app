// Validate finished QTY before submission
frappe.ui.form.on("Job Card", {
	validate: function(frm) {
    	if (frm.doc.status === "Completed") {
        	if (frm.doc.total_completed_qty !== frm.doc.total_qty) {
            	frappe.throw(`Completed quantity (${frm.doc.total_completed_qty}) must match the total quantity (${frm.doc.total_qty}) before completing this job.`);
        	}
    	}
	}
});

// Create Petty Cash Request
frappe.ui.form.on('Job Card', {
	refresh: function(frm) {
    	// Remove ONLY the "Material Request" button from the "Create" menu
    	frm.remove_custom_button('Material Request');

    	frm.add_custom_button('Create Petty Cash Request', () => {
        	frappe.new_doc('Petty Cash Request', {
            	job_card: frm.doc.name
        	}, 'Create');
    	});

		frm.add_custom_button('Create Damages and Returns', () => {
        	frappe.new_doc('Damages and Returns', {
            	job_card: frm.doc.name
        	}, 'Create');
    	});
	}
});
