frappe.ui.form.on("Job Card", {
	validate: function(frm) {
    	if (frm.doc.status === "Completed") {
        	if (frm.doc.total_completed_qty !== frm.doc.total_qty) {
            	frappe.throw(`Completed quantity (${frm.doc.total_completed_qty}) must match the total quantity (${frm.doc.total_qty}) before completing this job.`);
        	}
    	}
	}
});
