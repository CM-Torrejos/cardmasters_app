frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		
		// Artist Sheet Button Creation
		function set_artist_card_button() {
			frm.clear_custom_buttons();
			
			const invalid_statuses = ['On Hold', 'Cancelled', 'Closed', 'Draft'];
			
			if (!invalid_statuses.includes(frm.doc.status)) {
				frm.add_custom_button(__('Create Artist Card'), function() {
					frappe.new_doc('Artist Card', {
						sales_order: frm.doc.name,
						artist: frm.doc.custom_artist
					});
				}, __('Create'));
			}
		}
		
		// Custom Pill Append
		function set_custom_pill(doc) {
			$('span.custom-state-pill').remove();
			const state = frm.doc.workflow_state; // ← rename if needed
			if (!state) {
				console.log('[your_app] no workflow_state, skipping');
				return;
			}
			console.log('[your_app] custom workflow state:', state);
			
			// Map state → Frappe colour class
			const colorMap = {
				'Claiming':			'light-blue',
				'Pending':			'yellow',
				'Artist':				'blue',
				'Production':			'orange',
				'Claimed':			'green',
				'Rejected':			'red',
				// …etc
			};
			const color = colorMap[state] || 'gray';
			console.log('[your_app] using colour:', color);
			
			// Build pill using the *exact* same core classes
			const $pill = $('<span>')
			.addClass(`indicator-pill no-indicator-dot whitespace-nowrap custom-state-pill ${color}`)
			.text(state);
			
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
		
		// Call it on refresh
		set_custom_pill();
		set_artist_card_button();
		
		// Optional: re-run it after status changes dynamically
		frm.fields_dict.status.df.onchange = function() {
			set_artist_card_button();
			set_custom_pill();
		};
		
		
		// Work Order Progress HTML block
		if (!frm.doc.__islocal) {
			// frappe.show_alert("Fetching Work Orders..."); // Debugging message
			frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'Work Order',
					filters: { sales_order: frm.doc.name },
					fields: ['name', 'workflow_state', 'item_name', 'status']
				},
				callback: function(response) {
					// frappe.show_alert("Work Orders fetched: " + response.message.length); // Debug message
					console.log(response.message);
					
					if (response.message.length > 0) {
						let html = '<table class="table table-bordered"><tr><th>Work Order</th><th>Item</th><th>Form Status</th><th>Progress</th></tr>';
						response.message.forEach(wo => {
							html += `<tr>
                                    	<td><a href="/app/work-order/${wo.name}" target="_blank">${wo.name}</a></td>
                                    	<td>${wo.item_name}</td>
                                    	<td>${wo.status}</td>
                                    	<td>${wo.workflow_state}</td>
                                	</tr>`;
						});
						html += '</table>';
						frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
					} else {
						frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>No Work Orders found.</p>");
					}
				}
			});
		}
		
		// Display custom workflow state as pill
		// $('span.custom-state-pill').remove();
		// const state = frm.doc.workflow_state; // ← rename if needed
		// if (!state) {
		//   console.log('[your_app] no workflow_state, skipping');
		//   return;
		// }
		// console.log('[your_app] custom workflow state:', state);
		
		// // Map state → Frappe colour class
		// const colorMap = {
		//   'Claiming':			'light-blue',
		//   'Pending':			'yellow',
		//   'Artist':				'blue',
		//   'Production':			'orange',
		//   'Claimed':			'green',
		//   'Rejected':			'red',
		//   // …etc
		// };
		// const color = colorMap[state] || 'gray';
		// console.log('[your_app] using colour:', color);
		
		// // Build pill using the *exact* same core classes
		// const $pill = $('<span>')
		//   .addClass(`indicator-pill no-indicator-dot whitespace-nowrap custom-state-pill ${color}`)
		//   .text(state);
		
		// const $native = $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').first();
		// console.log('[your_app] native pills found:', $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').length);
		
		// if ($native.length) {
		//   $native.after($pill);
		//   console.log('[your_app] appended custom pill after native one');
		// } else {
		//   // fallback: stick it next to the title
		//   $('.page-head .title-area .flex').first().append($pill);
		//   console.log('[your_app] native pill not found, appended to title-area');
		// }
	},
	
	custom_sales_channel: function(frm){
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Sales Channel",
				filters: { name: frm.doc.custom_sales_channel },
				fieldname: "has_sales_partner"
			},
			callback: function(response) {
				console.log("im running")
				if (response.message) {
					let has_sales_partner = response.message.has_sales_partner;
					console.log(has_sales_partner)
					if (has_sales_partner){
						console.log('im supposed to set req to 1')
						frm.set_df_property('sales_partner', 'reqd', 1);
					}else{
						frm.set_df_property('sales_partner', 'reqd', 0);
					}
					
					
				}
				
				
			}
		});
	}
	
	
	
	
	// refresh: function(frm) {
	//     // Clear previous custom indicator to prevent duplicates on refresh
	//     frm.page.clear_indicator();
	//     const state = frm.doc.workflow_state;
	//     if (!state) {
	//         return;
	//     }
	
	//     // Map your workflow_state to a color
	//     const colorMap = {
	//         'Claiming': 'light-blue',
	//         'Pending': 'yellow',
	//         'Artist': 'blue',
	//         'Production': 'orange',
	//         'Claimed': 'green',
	//         'Rejected': 'red'
	//     };
	
	//     const color = colorMap[state] || 'gray';
	
	//     // Use the built-in function to add the indicator
	//     // The function returns the indicator element, which you can customize further if needed
	//     frm.page.add_indicator(state, color);
	// }
});