frappe.ui.form.on('Sales Order', {
	refresh: function(frm) {
		const invalid_statuses = ['On Hold', 'Cancelled', 'Closed'];

		// Artist Sheet Button Creation
		function set_artist_card_button() {
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

		// Add Credit Memo in Create Button
		if (!frm.is_new() && !invalid_statuses.includes(frm.doc.status)) {
			frm.add_custom_button(__('Issue Credit Memo'), function() {
				// Get the address display string (or empty string if null)
				let raw_address = frm.doc.address_display || "";
				
				// Clean HTML tags (replace <br> with comma, then strip other tags)
				let clean_address = raw_address
					.replace(/<br\s*[\/]?>/gi, ", ")       // 1. Replace all <br>, <br/>, or <BR> tags with a comma and space
					.replace(/<\/?[^>]+(>|$)/g, "")        // 2. Strip all other HTML tags (like <div> or <span>)
					.replace(/\s\s+/g, ' ')                // 3. Collapse multiple consecutive spaces into a single space
					.trim()                                // 4. Remove whitespace and newlines from the start and end of the string
					.replace(/,\s*$/, "");                 // 5. Remove a comma (and any trailing space) if it's at the very end

				frappe.new_doc('Credit Memo', {
					sales_order: frm.doc.name,
					customer: frm.doc.customer,
					address: frm.doc.customer_address,
					address_display: clean_address,
				});
			}, __('Create'));
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
					fields: ['name', 'workflow_state', 'item_name', 'status', 'qty', 'custom_item_specifics', 'custom_particulars', 'custom_bypass', 'sales_order_item']
				},
				callback: function(response) {
					let work_orders = response.message || [];
					
					let html = `
						<style>
							.custom-wo-table { table-layout: fixed; width: 100%; border-collapse: collapse; }
							.custom-wo-table td, .custom-wo-table th { 
								white-space: normal !important; 
								word-wrap: break-word; 
								vertical-align: top; 
								padding: 10px 8px;
								font-size: 0.9em;
								border-bottom: 1px solid var(--border-color);
							}
							/* Standard row coloring */
							.status-concluded { color: var(--green-600, #28a745); font-weight: bold; }
							
							/* No Work Order - Red Text only, No background */
							.no-wo-row { 
								color: #ff5858 !important; 
								font-style: italic; 
							}
							.missing-label { 
								font-weight: bold; 
								color: #ff5858 !important; 
							}
						</style>
						<table class="table table-bordered custom-wo-table">
							<thead>
								<tr>
									<th style="width: 12%;">Work Order</th>
									<th style="width: 12%;">Item</th>
									<th style="width: 6%;">Qty</th>
									<th style="width: 13%;">Specifics</th>
									<th style="width: 13%;">Particulars</th>
									<th style="width: 14%;">Production Status</th>
									<th style="width: 15%;">Consumption</th>
									<th style="width: 15%;">Claiming Status</th>
								</tr>
							</thead>
							<tbody>`;

					frm.doc.items.forEach(so_item => {
						let linked_wos = work_orders.filter(wo => wo.sales_order_item === so_item.name);
						let total_wo_qty = 0;

						// 1. Existing Work Orders
						linked_wos.forEach(wo => {
							total_wo_qty += wo.qty;

							let production_status = wo.workflow_state || "";
							const concluded_states = ["In Claiming", "Pending Claiming", "Pending Consumption"];
							
							if (concluded_states.includes(wo.workflow_state)) {
								production_status = `<span class="status-concluded">Production Concluded</span>`;
							} else if (wo.workflow_state === "In Production") {
								production_status = "In Production";
							} else if (wo.workflow_state === "Draft") {
								production_status = "Draft";
							} else if (wo.workflow_state === "Not Started") {
								production_status = "Not Started";
							}

							let consumption_status = wo.status === "Completed" ? "Consumption entry submitted" : "No consumption entry submitted";
							
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
									<td>${wo.qty}</td>
									<td>${wo.custom_item_specifics || ""}</td>
									<td>${wo.custom_particulars || ""}</td>
									<td>${production_status}</td>
									<td>${consumption_status}</td>
									<td>${claiming_status}</td>
								</tr>`;
						});

						// 2. Remaining/Missing Balance Row
						let remaining_qty = so_item.qty - total_wo_qty;
						if (remaining_qty > 0) {
							html += `
								<tr class="no-wo-row">
									<td class="missing-label">No Work Order</td>
									<td>${so_item.item_name}</td>
									<td>${remaining_qty}</td>
									<td>${so_item.custom_item_specifics || ""}</td>
									<td>${so_item.custom_particulars || ""}</td>
									<td>Pending Creation</td>
									<td>N/A</td>
									<td>N/A</td>
								</tr>`;
						}
					});

					html += '</tbody></table>';
					frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
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
