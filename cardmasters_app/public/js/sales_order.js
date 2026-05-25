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

		if (!frm.is_new() && !invalid_statuses.includes(frm.doc.status)) {
			frm.add_custom_button(__('Issue Complaint'), function() {
				frappe.new_doc('Complaint', {
					sales_order: frm.doc.name,
					customer: frm.doc.customer,
				});
			}, __('Create'));
		}

		if (!frm.is_new() && !invalid_statuses.includes(frm.doc.status)) {
			frm.add_custom_button(__('Issue Damages/Returns'), function() {
				frappe.new_doc('Damages and Returns', {
					sales_order: frm.doc.name,
					date: 'Today',
					date_of_damage_or_return: 'Today'
				});
			}, __('Create'));
		}

		if (!frm.is_new() && !invalid_statuses.includes(frm.doc.status)) {
			frm.add_custom_button(__('Create Quotation'), function() {
                frappe.model.open_mapped_doc({
                    method: "cardmasters_app.cardmasters_app.api.sales_order.make_quotation_from_so",
                    frm: frm
                });
            }, __("Create"));
		}

		// Custom Pill Append
		setTimeout(() => {
            set_custom_pill(frm);
        }, 100);


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

		if (frm.doc.docstatus === 1 && !frm.custom_update_overridden) {
            
            // 1. Store a copy of Frappe's original save function
            const original_save = frm.save.bind(frm);
            
            // 2. Overwrite the save function with our custom logic
            frm.save = function(action, callback, btn, on_error) {
                
                // When clicking the yellow 'Update' button, the action is usually 'Update'
                // If it is an Update, we pause and check for discrepancies
                let is_update = action === 'Update' || (!action && frm.doc.docstatus === 1);
                
                if (is_update) {
                    // Return a promise so the UI loading state behaves normally
                    return new Promise((resolve, reject) => {
                        frappe.call({
                            method: "cardmasters_app.cardmasters_app.api.sales_order.check_wo_discrepancy",
                            args: {
                                so_name: frm.doc.name,
                                items: JSON.stringify(frm.doc.items)
                            },
                            callback: function(r) {
                                if (r.message) {
                                    // Discrepancy found! Show the prompt.
                                    frappe.confirm(
                                        r.message,
                                        function() {
                                            // User clicked "Yes": Proceed with the original Update
                                            resolve(original_save(action, callback, btn, on_error));
                                        },
                                        function() {
                                            // User clicked "No": Cancel the Update process entirely
                                            reject();
                                        }
                                    );
                                } else {
                                    // No discrepancies found: Proceed with the Update silently
                                    resolve(original_save(action, callback, btn, on_error));
                                }
                            },
                            error: function() {
                                // If the Python API fails, reject the save to be safe
                                reject();
                            }
                        });
                    });
                } else {
                    // If it's not an update (e.g., Cancel), just run the normal save
                    return original_save(action, callback, btn, on_error);
                }
            };
            
            // Flag it so we don't accidentally override the override if refresh() runs twice
            frm.custom_update_overridden = true;
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
	},

	before_workflow_action: async (frm) => {
		// Replace 'Approve' with your exact workflow action/transition name
		if (frm.selected_workflow_action === 'Declare Lost') {
			
			// Return a Promise to pause the workflow execution until the dialog is handled
			return new Promise((resolve, reject) => {
				frappe.dom.unfreeze();
				frappe.prompt([
					{
						// Define the field inside the popup dialog
						label: 'Input Lost Reason',
						fieldname: 'custom_lost_reason',
						fieldtype: 'Link', // Can be Data, Text, Select, etc.
						options: 'Sales Order Lost Reason',
						reqd: 1 // 1 means mandatory, 0 means optional
					}
				],
				function(values){
					frappe.db.set_value(frm.doctype, frm.docname, 'custom_lost_reason', values.custom_lost_reason)
						.then(() => {
							// 2. Update the local form so it doesn't look out of sync
							frm.set_value('custom_lost_reason', values.custom_lost_reason);
							
							// 3. Resolve the promise to let the workflow finish its transition
							resolve();
						})
						.catch(() => {
							frappe.msgprint(__('Failed to save to database.'));
							reject(); // Stop workflow if the DB write fails
						});
				},
				'Input Required', // Title of the Dialog Box
				'Submit' // Text on the Dialog Button
				);
				
				// If the user closes the dialog box without submitting, cancel the workflow action
				$('.frappe-control[data-fieldname="custom_lost_reason"]').closest('.modal').on('hidden.bs.modal', function() {
					reject(); 
				});
			});
		}
	},

	validate: function(frm) {
        // 1. If a project is already linked, proceed with save normally
        if (frm.doc.project) {
            return;
        }

        let needs_project = false;

        // 2. Loop through items to check conditions
        if (frm.doc.items && frm.doc.items.length > 0) {
            for (let item of frm.doc.items) {
                // Check if amount is 100k+ OR item_code ends with '-PRJ'
                if (item.amount >= 100000 || (item.item_code && item.item_code.endsWith('-PRJ'))) {
                    needs_project = true;
                    break;
                }
            }
        }

        // 3. If condition is met and we aren't already processing a prompt
        if (needs_project && !frm.doc.__project_creation_in_progress) {
            
            // Halt the standard save process so we can wait for user input
            frappe.validated = false; 

            // Show prompt to the user
            frappe.prompt([
                {
                    // Adding an HTML field to display the message
                    fieldtype: 'HTML',
                    fieldname: 'instruction_message',
                    options: '<div style="margin-bottom: 15px; font-size: 13px; color: var(--text-muted);">This Sales Order contains high-value items (100K+) or project-specific items.<br><br><b>A Project is required to proceed.</b> Please enter a unique name below to automatically create and link the project.</div>'
                },
                {
                    label: 'Project Name',
                    fieldname: 'project_name',
                    fieldtype: 'Data',
                    reqd: 1
                }
            ], function(values){
                // ON CONFIRM: Set a flag to prevent infinite loops
                frm.doc.__project_creation_in_progress = true; 
                
                // Show a loading indicator
                frappe.show_progress('Creating Project', 50, 100, 'Please wait');

                // Create the Project document via API
                frappe.call({
                    method: "frappe.client.insert",
                    args: {
                        doc: {
                            doctype: "Project",
                            project_name: values.project_name
                        }
                    },
                    callback: function(r) {
                        frappe.hide_progress();
                        if (r.message) {
                            // Link the newly created Project to the Sales Order
                            frm.set_value('project', r.message.name);
                            frappe.show_alert({message: `Project ${r.message.name} created and linked.`, indicator: 'green'});
                            
                            // Reset the flag right before saving so the system is clean
                            frm.doc.__project_creation_in_progress = false;
                            
                            // Trigger the save process again
                            frm.save();
                        }
                    },
                    // ERROR HANDLER: Closes the loophole for duplicate names
                    error: function(r) {
                        frappe.hide_progress();
                        // Reset flag if project creation fails so the prompt can trigger again
                        frm.doc.__project_creation_in_progress = false; 
                    }
                });
            }, 'Project Required', 'Create & Save');
        }
    }

});


function set_custom_pill(frm) {
    // 1. SCOPE TO CURRENT FORM: This prevents the pill from bleeding into other pages
    const $wrapper = frm.page.wrapper;
    
    // 2. Remove existing custom pill (within this wrapper only) to prevent duplicates
    $wrapper.find('.custom-state-pill').remove();
    
    const state = frm.doc.workflow_state; 
    if (!state) {
        // console.log('[your_app] no workflow_state, skipping');
        return;
    }
    
    // Map state -> Frappe color class
    const colorMap = {
        'Claiming':             'light-blue',
        'Pending':              'yellow',
        'Artist':               'blue',
        'Production':           'orange',
        'Claimed':              'green',
        'Rejected':             'red',
        'Production Concluded': 'green'
    };
    const color = colorMap[state] || 'gray';
    
    // Build pill (Added 'ml-2' for a slight left margin so it doesn't stick to the native pill)
    const $pill = $('<span>')
        .addClass(`indicator-pill no-indicator-dot whitespace-nowrap ml-2 custom-state-pill ${color}`)
        .text(state);
    
    // 3. Find the native pill ONLY within this specific form's wrapper
    const $native = $wrapper.find('span.indicator-pill.no-indicator-dot.whitespace-nowrap').first();
    
    if ($native.length) {
        $native.after($pill);
    } else {
        // Fallback: append to title area of THIS specific wrapper
        $wrapper.find('.page-head .title-area .flex').first().append($pill);
    }
}