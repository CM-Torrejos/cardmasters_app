// Create Petty Cash Request
frappe.ui.form.on('Sales Order', {
	refresh(frm) {
    	if (!frm.is_new()) {
        	frm.add_custom_button('Petty Cash Request', () => {
            	frappe.new_doc('Petty Cash Request', {
                	sales_order: frm.doc.name
            	});
        	}, 'Create'); 
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
        	}, __('Create')); 
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
                	fields: ['name', 'status', 'production_item']
            	},
            	callback: function(response) {
                	// frappe.show_alert("Work Orders fetched: " + response.message.length); // Debug message
                	console.log(response.message);

                	if (response.message.length > 0) {
                    	let html = '<table class="table table-bordered"><tr><th>Work Order</th><th>Item</th><th>Progress</th></tr>';
                    	response.message.forEach(wo => {
                        	html += `<tr>
                                    	<td><a href="/app/work-order/${wo.name}" target="_blank">${wo.name}</a></td>
                                    	<td>${wo.production_item}</td>
                                    	
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


// your_app/public/js/sales_order_workflow.js

frappe.ui.form.on('Sales Order', {
	refresh(frm) {
	  // 1) Remove any old copy
	  $('span.custom-state-pill').remove();
  
	  // 2) Grab your custom workflow field
	  const state = frm.doc.workflow_state; // ← rename if needed
	  if (!state) {
		console.log('[your_app] no workflow_state, skipping');
		return;
	  }
	  console.log('[your_app] custom workflow state:', state);
  
	  // 3) Map state → Frappe colour class
	  const colorMap = {
		'Claiming':            'light-blue',
		'Pending':			   'yellow',
		'Artist':			   'blue',
		'Production':		   'orange',
		'Claimed':             'green',
		'Rejected':            'red',
		// …etc
	  };
	  const color = colorMap[state] || 'gray';
	  console.log('[your_app] using colour:', color);
  
	  // 4) Build your pill using the *exact* same core classes
	  const $pill = $('<span>')
		.addClass(`indicator-pill no-indicator-dot whitespace-nowrap custom-state-pill ${color}`)
		.text(state);
  
	  // 5) Find the first native pill and insert after it
	  const $native = $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').first();
	  console.log('[your_app] native pills found:', $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').length);
  
	  if ($native.length) {
		$native.after($pill);
		console.log('[your_app] appended custom pill after native one');
	  } else {
		// fallback: stick it next to the title
		$('.page-head .title-area .flex').first().append($pill);
		console.log('[your_app] native pill not found, appended to title-area');
	  }
	}
  });