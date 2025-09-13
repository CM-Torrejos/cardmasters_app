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
		if (frm.doc.custom_sales_order) {
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.event_handlers.get_sales_order.get_sales_order_html',
				args: {
					sales_order_name: frm.doc.custom_sales_order
				},
				callback: function(r) {
					if (r.message) {
						// … inside your callback …
						const iframe = document.createElement("iframe");
						iframe.src = "about:blank";      // ← add this!
						iframe.style.width  = "800px";
						iframe.style.height = "1000px";
						iframe.style.border = "1px solid #ccc";
						iframe.setAttribute("scrolling", "no");
						
						// install onload _before_ appending
						iframe.onload = function() {
							const doc = iframe.contentWindow.document;
							doc.open();
							doc.write(r.message);
							doc.close();
							
							// hide the toolbar once content is in
							setTimeout(() => {
								const style = doc.createElement("style");
								style.innerHTML = `
								body { margin: 0; padding: 0; overflow: hidden; }
								.print-format-toolbar { display: none !important; }
								`;
								doc.head.appendChild(style);
							}, 100);
						};
						
						frm.fields_dict.custom_sales_order_print.$wrapper
						.empty()
						.append(iframe);
						
					}
				}
			});
		}

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

		// frm.add_custom_button(__('Material Request'), () => {
		// frappe.model.open_mapped_doc({
		// 	method: 'erpnext.manufacturing.doctype.job_card.job_card.make_material_request',
		// 	source_name: frm.doc.name
		// });
		// }, __('Create'));

		frm.add_custom_button(__('Material Request'), function() {
				frappe.new_doc('Material Request', {
					work_order: frm.doc.work_order,
					material_request_type: 'Material Transfer'
					});
		}, __('Create'));
		
		frm.add_custom_button(__('Material Transfer'), () => {
		frappe.model.open_mapped_doc({
			method: 'erpnext.manufacturing.doctype.job_card.job_card.make_stock_entry',
			source_name: frm.doc.name
		});
		}, __('Create'));
	}
});

