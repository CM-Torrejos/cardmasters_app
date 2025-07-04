// Validate finished QTY before submission
frappe.ui.form.on("Job Card", {
	validate: function(frm) {
    	if (frm.doc.status === "Completed") {
        	if (frm.doc.total_completed_qty !== frm.doc.total_qty) {
            	frappe.throw(`Completed quantity (${frm.doc.total_completed_qty}) must match the total quantity (${frm.doc.total_qty}) before completing this job.`);
        	}
    	}
	},

	refresh: function(frm) {
		if (!frm.doc.__islocal) {
        	// frappe.show_alert("Fetching Work Orders..."); // Debugging message
        	frappe.call({
            	method: 'frappe.client.get_list',
            	args: {
                	doctype: 'Job Card',
                	filters: [['Job Card', 'work_order', '=', frm.doc.work_order],
					['Job Card', 'name',     '!=', frm.doc.name]],
                	fields: ['operation', 'status', 'item_name']
            	},
            	callback: function(response) {
                	// frappe.show_alert("Work Orders fetched: " + response.message.length); // Debug message
                	console.log(response.message);

                	if (response.message.length > 0) {
                    	let html = '<table class="table table-bordered"><tr><th>Job Card</th><th>Item</th><th>Status</th></tr>';
                    	response.message.forEach(jc => {
                        	html += `<tr>
                                    	<td>${jc.operation}</td>
                                    	<td>${jc.item_name}</td>
                                    	<td>${jc.status}</td>
                                	</tr>`;
                    	});
                    	html += '</table>';
                    	frm.fields_dict['custom_linked_jobs'].$wrapper.html(html);
                	} else {
                    	frm.fields_dict['custom_linked_jobs'].$wrapper.html("<p>No other job cards found.</p>");
                	}
            	}
        	});
    	} else {
        	frappe.show_alert("Job Card is not yet saved. Job Cards will load after saving.");
        	frm.fields_dict['custom_linked_jobs'].$wrapper.html("<p>Save the Job Card to view</p>");
    	}
	}
});

