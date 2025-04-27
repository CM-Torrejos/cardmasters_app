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

// TODO: Optimize Script
// Show Work Order Progress
frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
    	// Ensure the Sales Order is saved before fetching Work Orders
    	if (!frm.doc.__islocal) {
        	// frappe.show_alert("Fetching Work Orders..."); // Debugging message

        	frappe.call({
            	method: 'frappe.client.get_list',
            	args: {
                	doctype: 'Work Order',
                	filters: { sales_order: frm.doc.name },
                	fields: ['name', 'status', 'production_item', 'custom_production_type']
            	},
            	callback: function(response) {
                	// frappe.show_alert("Work Orders fetched: " + response.message.length); // Debug message
                	console.log(response.message);

                	if (response.message.length > 0) {
                    	let html = '<table class="table table-bordered"><tr><th>Work Order</th><th>Item</th><th>Production Type</th><th>Progress</th></tr>';
                    	response.message.forEach(wo => {
                        	html += `<tr>
                                    	<td><a href="/app/work-order/${wo.name}" target="_blank">${wo.name}</a></td>
                                    	<td>${wo.production_item}</td>
                                    	<td>${wo.custom_production_type || 'N/A'}</td>
                                    	<td>${wo.status}</td>
                                	</tr>`;
                    	});
                    	html += '</table>';
                    	frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
                	} else {
                    	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>No Work Orders found.</p>");
                	}
            	}
        	});
    	} else {
        	frappe.show_alert("Sales Order is not yet saved. Work Orders will load after saving.");
        	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>Save the Sales Order to view Work Orders.</p>");
    	}
	}
});
