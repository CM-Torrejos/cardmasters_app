// TODO: optimize script
frappe.ui.form.on('Work Order', {
	refresh: function(frm) {
    	// Ensure the Work Order is saved before fetching Job Cards
    	if (!frm.doc.__islocal) {
        	frappe.call({
            	method: 'frappe.client.get_list',
            	args: {
                	doctype: 'Job Card',
                	filters: { work_order: frm.doc.name },
                	fields: ['name', 'status', 'operation', 'employee']
            	},
            	callback: function(response) {
                	console.log(response.message);

                	if (response.message.length > 0) {
                    	let html = '<table class="table table-bordered"><tr><th>Job Card</th><th>Operation</th><th>Employee</th><th>Status</th></tr>';
                    	response.message.forEach(jc => {
                        	html += `<tr>
                                    	<td><a href="/app/job-card/${jc.name}" target="_blank">${jc.name}</a></td>
                                    	<td>${jc.operation}</td>
                                    	<td>${jc.employee || 'N/A'}</td>
                                    	<td>${jc.status}</td>
                                	</tr>`;
                    	});
                    	html += '</table>';
                    	frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
                	} else {
                    	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>No Job Cards found.</p>");
                	}
            	}
        	});
    	} else {
        	frappe.show_alert("Work Order is not yet saved. Job Cards will load after saving.");
        	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>Save the Work Order to view Job Cards.</p>");
    	}
	}
});
