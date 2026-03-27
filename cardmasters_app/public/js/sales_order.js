frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		
		// Artist Sheet Button Creation
		function set_artist_card_button() {
			
			const invalid_statuses = ['On Hold', 'Cancelled', 'Closed'];
			
			if (!invalid_statuses.includes(frm.doc.status)) {
				frm.add_custom_button(__('Create Artist Card'), function() {
					frappe.new_doc('Artist Card', {
						sales_order: frm.doc.name,
						customer: frm.doc.customer,
						deadline: frm.doc.delivery_date,
						date_created: frappe.datetime.get_today(),
						rush_order: frm.doc.custom_rush_order,
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
				'Production Concluded': 	'green'
				// …etc
			};
			const color = colorMap[state] || 'gray';
			
			// Build pill using the *exact* same core classes
			const $pill = $('<span>')
			.addClass(`indicator-pill no-indicator-dot whitespace-nowrap custom-state-pill ${color}`)
			.text(state);
			
			const $native = $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').first();
			
			if ($native.length) {
				$native.after($pill);
			} else {
				// fallback: stick it next to the title
				$('.page-head .title-area .flex').first().append($pill);
				console.log('[your_app] native pill not found, appended to title-area');
			}
		}
		
		// Call it on refresh
		set_custom_pill();


		// TODO: This shit dont work blud
		// if (!frappe.user.has_role('CM Head Approver') && !frappe.user.has_role('System Manager')) {
        //     frm.remove_custom_button('Update Items');
        // }

		if (frappe.user.has_role('CM Artist Assigner') || frappe.user.has_role('System Manager')) {
            set_artist_card_button();
        }

		
		// Optional: re-run it after status changes dynamically
		frm.fields_dict.status.df.onchange = function() {
			set_artist_card_button();
			set_custom_pill();
		};
		
		
		// Work Order Progress HTML block
		if (!frm.doc.__islocal) {
			frappe.call({
				method: 'frappe.client.get_list',
				args: {
					doctype: 'Work Order',
					filters: {
						sales_order: frm.doc.name,
						docstatus: ["!=", 2] // Exclude Cancelled
					},
					fields: ['name', 'workflow_state', 'item_name', 'status', 'qty', 'custom_item_specifics', 'custom_particulars', 'custom_bypass']
				},
				callback: function(response) {
					if (response.message && response.message.length > 0) {
						let html = `
							<style>
								.custom-wo-table { table-layout: fixed; width: 100%; }
								.custom-wo-table td, .custom-wo-table th { 
									white-space: normal !important; 
									word-wrap: break-word; 
									vertical-align: top; 
									padding: 8px;
								}
							</style>
							<table class="table table-bordered custom-wo-table">
								<thead>
									<tr>
										<th style="width: 14%;">Work Order</th>
										<th style="width: 14%;">Item</th>
										<th style="width: 7%;">Qty</th>
										<th style="width: 15%;">Specifics</th>
										<th style="width: 15%;">Particulars</th>
										<th style="width: 15%;">Consumption</th>
										<th style="width: 20%;">Claiming Status</th>
									</tr>
								</thead>
								<tbody>`;

						response.message.forEach(wo => {
							// Consumption Status Logic
							let consumption_status = wo.status === "Completed" 
								? "Consumption entry submitted" 
								: "No consumption entry submitted";

							// Claiming Status Logic with Bypass check
							let claiming_status = "Not In Claiming";
							
							if (wo.custom_bypass == 1) {
								claiming_status = "In Claiming (Bypassed)";
							} else if (wo.workflow_state === "In Claiming") {
								claiming_status = "In Claiming";
							}

							html += `
								<tr>
									<td><a href="/app/work-order/${wo.name}" target="_blank"><b>${wo.name}</b></a></td>
									<td>${wo.item_name || ""}</td>
									<td>${wo.qty || 0}</td>
									<td>${wo.custom_item_specifics || ""}</td>
									<td>${wo.custom_particulars || ""}</td>
									<td>${consumption_status}</td>
									<td>${claiming_status}</td>
								</tr>`;
						});

						html += '</tbody></table>';
						frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
					} else {
						frm.fields_dict['custom_progress_summary'].$wrapper.html("<p class='text-muted'>No active Work Orders found.</p>");
					}
				}
			});
		}

		if (frm.doc.docstatus === 1) {
    		// Call our server-side python method
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.outstanding_balance.get_sales_order_outstanding',
				args: {
					so_name: frm.doc.name
				},
				callback: function(r) {
					if (r.message !== undefined) {
						
						// --- THE FIX ---

						// 1. Set the value directly in the form's local data object.
						//    This does NOT mark the form as "dirty".
						frm.doc.custom_outstanding_balance = r.message;

						// 2. Tell the UI to re-render just this one field
						//    to show the new value from frm.doc.
						frm.refresh_field('custom_outstanding_balance');
					}
				}
			});
			
			// REMOVED: doc.save(ignore_permissions=true)
		}
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
	},

	// Client Script for Sales Order
    custom_grant: function(frm) {
    if (frm.doc.custom_grant) {
        frappe.db.get_value('Grant', frm.doc.custom_grant, 'available_balance', (r) => {
            if (r && r.available_balance !== undefined) {
                let available = r.available_balance;
                let color = (available < frm.doc.grand_total) ? 'red' : 'blue';
                frm.set_intro(`Current Grant Balance: ${format_currency(available)}`, color);
            }
        });
    } else {
        frm.set_intro(null);
    }
}
	
});
