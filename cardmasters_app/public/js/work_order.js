frappe.ui.form.on('Work Order', {
	refresh: function(frm) {
		console.log('hello world')
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
		
		// Optional: re-run it after status changes dynamically
		frm.fields_dict.status.df.onchange = function() {
			set_custom_pill();
		};

		if (frm.doc.sales_order) {
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.event_handlers.get_sales_order.get_sales_order_html',
				args: {
					sales_order_name: frm.doc.sales_order
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

	

});
