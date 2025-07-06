frappe.ui.form.on('Work Order', {
	refresh: function(frm) {
		console.log('hello world')
		if (frm.doc.sales_order) {
			console.log('hello world')
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.event_handlers.get_sales_order.get_sales_order_html',
				args: {
					sales_order_name: frm.doc.sales_order
				},
				callback: function(r) {
					if (r.message) {
						const iframe = document.createElement("iframe");
						iframe.style.width = "800px";
						iframe.style.height = "1000px";
						iframe.style.border = "1px solid #ccc";
						iframe.style.overflow = "hidden";
						iframe.setAttribute("scrolling", "no");
						
						frm.fields_dict.custom_sales_order_print.$wrapper.empty().append(iframe);
						
						iframe.onload = function () {
							const doc = iframe.contentWindow.document;
							doc.open();
							doc.write(r.message);
							doc.close();
							
							// Wait for toolbar to be added before styling
							setTimeout(() => {
								const style = doc.createElement("style");
								style.innerHTML = `
                body { margin: 0; padding: 0; overflow: hidden; }
                .print-format-toolbar { display: none !important; }
            `;
								doc.head.appendChild(style);
							}, 100); // wait 100ms
						};
					}
				}
			});
		}

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

		frm.add_custom_button('Material Request', () => {
			frappe.new_doc('Material Request', {
				material_request_type: 'Material Transfer',
				work_order : frm.doc.name,
				set_from_warehouse: 'MASTER WAREHOUSE - CM CDO'
			})
		})
	},


	// // TODO: Ensure that this code only runs when the thing is submitted already.
	// refresh: (frm) => {
	// 	frm.add_custom_button('Material Request', () => {
	// 		frappe.new_doc('Material Request', {
	// 			material_request_type: 'Material Transfer',
	// 			work_order : frm.doc.name,
	// 			set_from_warehouse: 'MASTER WAREHOUSE - CM CDO'
	// 		})
	// 	})
	// }
});
