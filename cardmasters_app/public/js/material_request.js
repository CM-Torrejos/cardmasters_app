frappe.ui.form.on('Material Request', {    
    refresh: function(frm) {
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

        if (frm.doc.docstatus === 1 && frm.doc.material_request_type === 'Customer Provided') {
            // Remove the default "Material Receipt" button (if present)
            setTimeout(() => {
                frm.page.remove_inner_button(__('Material Receipt'), __('Create'));
            }, 100);

            // Add our custom "Receive Customer Provided Item" button
            frm.add_custom_button(__('Receive Customer Provided Item'), async () => {
                try {
                    // Call the backend Python function
                    const response = await frappe.call({
                        method: 'cardmasters_app.cardmasters_app.api.material_request.make_rcpi_stock_entry',
                        args: {
                            material_request_name: frm.doc.name
                        }
                    });

                    // If the Python call returned a Stock Entry name, redirect to it
                    if (response.message) {
                        frappe.set_route('Form', 'Stock Entry', response.message);
                    }
                } catch (err) {
                    // In case something goes wrong, show a frappe error
                    frappe.show_alert({
                        message: __('Could not create the Stock Entry: {0}', [err.message]),
                        indicator: 'red'
                    });
                }
            }, __('Create'));
        }
    },
    
    validate: function(frm) {
        // Only enforce when Purpose is exactly "Customer Provided"
        // Necessary since stock entry batching assumes all items in the MR are from the same sales order
        if (frm.doc.material_request_type === 'Customer Provided') {
            // If there are no items, nothing to check
            console.log('validate function running')
            if (!frm.doc.items || frm.doc.items.length === 0) {
                return;
            }
            
            // Collect all sales_order values from each row
            let sales_orders = frm.doc.items.map(function(row) {
                return row.sales_order || null;
            });
            
            // If any row has no sales_order set, throw immediately
            for (let i = 0; i < sales_orders.length; i++) {
                if (!sales_orders[i]) {
                    frappe.throw(__(
                        'Row #{0} must have a Sales Order when Purpose is "Customer Provided".',
                        [frm.doc.items[i].idx]
                    ));
                }
            }
            
            // Now check that they’re all identical
            let first_so = sales_orders[0];
            let mismatch = sales_orders.some(function(so) {
                return so !== first_so;
            });
            
            if (mismatch) {
                frappe.throw(__('All items must reference the same Sales Order when Purpose is "Customer Provided".'));
            }
        }
    },
}); 
