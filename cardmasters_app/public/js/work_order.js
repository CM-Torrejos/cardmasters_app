frappe.ui.form.on('Work Order', {
	setup: function(frm) {
		filter_work_order_make_buttons(frm);

		// Cache the original button builder
		const original_add_button = frm.add_custom_button.bind(frm);

		// Gate standard Work Order buttons and rename allowed material transfer action.
		frm.add_custom_button = function(label, action, group) {
			if (is_work_order_button(label, 'Create Pick List')) {
				return $();
			}

			if (is_work_order_button_group(group, 'Status') && !has_work_order_status_action_permissions(frm)) {
				return $();
			}

			if (
				is_work_order_button(label, 'Create Job Card') &&
				(!frappe.model.can_create('Job Card') || cardmasters_job_cards_disabled())
			) {
				return $();
			}

			if (is_work_order_button(label, 'Start')) {
				if (!frm.has_perm('read') || !frappe.model.can_create('Stock Entry')) {
					return $();
				}

				let $btn = original_add_button(__('Withdraw'), action, group);
				$btn.removeClass('btn-default').addClass('btn-primary');
				return $btn;
			}

			// Build all other buttons normally
			return original_add_button(label, action, group);
		};
	},
	
	refresh: function(frm) {
		const invalid_statuses = ['On Hold', 'Cancelled', 'Closed'];
		filter_work_order_make_buttons(frm);

		setTimeout(() => {
			if(frm.custom_buttons['Withdraw']) {
				frm.change_custom_button_type('Withdraw', null, 'primary');
				
				let $btn = frm.page.get_custom_button('Withdraw');
				if($btn) {
					$btn.text(__('Withdraw'));
				}
			}
		}, 15);
		
		update_wo_installation(frm);
		// function set_custom_pill(doc) {
		// 	$('span.custom-state-pill').remove();
		// 	const state = frm.doc.workflow_state; // ← rename if needed
		// 	if (!state) {
		// 		console.log('[your_app] no workflow_state, skipping');
		// 		return;
		// 	}
		// 	console.log('[your_app] custom workflow state:', state);
			
		// 	// Map state → Frappe colour class
		// 	const colorMap = {
		// 		'Claiming':			'light-blue',
		// 		'Pending':			'yellow',
		// 		'Artist':				'blue',
		// 		'Production':			'orange',
		// 		'Claimed':			'green',
		// 		'Rejected':			'red',
		// 		// …etc
		// 	};
		// 	const color = colorMap[state] || 'gray';
		// 	console.log('[your_app] using colour:', color);
			
		// 	// Build pill using the *exact* same core classes
		// 	const $pill = $('<span>')
		// 	.addClass(`indicator-pill no-indicator-dot whitespace-nowrap custom-state-pill ${color}`)
		// 	.text(state);
			
		// 	const $native = $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').first();
		// 	console.log('[your_app] native pills found:', $('span.indicator-pill.no-indicator-dot.whitespace-nowrap').length);
			
		// 	if ($native.length) {
		// 		$native.after($pill);
		// 		console.log('[your_app] appended custom pill after native one');
		// 	} else {
		// 		// fallback: stick it next to the title
		// 		$('.page-head .title-area .flex').first().append($pill);
		// 		console.log('[your_app] native pill not found, appended to title-area');
		// 	}
		// }

		// Call it on refresh
		// set_custom_pill();
		
		// Optional: re-run it after status changes dynamically
		// frm.fields_dict.status.df.onchange = function() {
		// 	set_custom_pill();
		// };

		// if (cardmasters.utils && cardmasters.utils.sales_order_print_preview) {
        //     cardmasters.utils.sales_order_print_preview(frm);
        // } else {
        //     console.error('Cardmasters Utils not loaded. Check hooks.py');
        // }

    	// if (!frm.doc.__islocal) {
        // 	frappe.call({
        //     	method: 'frappe.client.get_list',
        //     	args: {
        //         	doctype: 'Job Card',
        //         	filters: { work_order: frm.doc.name },
        //         	fields: ['name', 'status', 'operation', 'employee']
        //     	},
        //     	callback: function(response) {
        //         	console.log(response.message);

        //         	if (response.message.length > 0) {
        //             	let html = '<table class="table table-bordered"><tr><th>Job Card</th><th>Operation</th><th>Employee</th><th>Status</th></tr>';
        //             	response.message.forEach(jc => {
        //                 	html += `<tr>
        //                             	<td><a href="/app/job-card/${jc.name}" target="_blank">${jc.name}</a></td>
        //                             	<td>${jc.operation}</td>
        //                             	<td>${jc.employee || 'N/A'}</td>
        //                             	<td>${jc.status}</td>
        //                         	</tr>`;
        //             	});
        //             	html += '</table>';
        //             	frm.fields_dict['custom_progress_summary'].$wrapper.html(html);
        //         	} else {
        //             	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>No Job Cards found.</p>");
        //         	}
        //     	}
        // 	});
    	// } else {
        // 	frappe.show_alert("Work Order is not yet saved. Job Cards will load after saving.");
        // 	frm.fields_dict['custom_progress_summary'].$wrapper.html("<p>Save the Work Order to view Job Cards.</p>");
    	// }

		

		// frm.add_custom_button('Material Request', () => {
		// 	frappe.new_doc('Material Request', {
		// 		material_request_type: 'Material Transfer',
		// 		work_order : frm.doc.name,
		// 		set_from_warehouse: 'MASTER WAREHOUSE - CM CDO'
		// 	})
		// })

		if (frm.doc.docstatus === 1 && has_work_order_status_action_permissions(frm)) {
            frm.add_custom_button(__('Update Details'), function() {
                let d = new frappe.ui.Dialog({
                    title: __('Update Work Order Details'),
                    size: 'extra-large',
                    fields: [
                        {
                            label: 'Quantity',
                            fieldname: 'qty',
                            fieldtype: 'Float',
                            default: frm.doc.qty,
                            reqd: 1
                        },
                        {
                            label: 'Item Specifics',
                            fieldname: 'custom_item_specifics',
                            fieldtype: 'Small Text',
                            default: frm.doc.custom_item_specifics
                        },
                        {
                            label: 'Particulars',
                            fieldname: 'custom_particulars',
                            fieldtype: 'Small Text',
                            default: frm.doc.custom_particulars
                        },
                        {
                            label: __('Operations'),
                            fieldname: 'operations',
                            fieldtype: 'Table',
                            options: 'Work Order Operation',
                            cannot_add_rows: false,
                            cannot_delete_rows: false,
                            in_place_edit: true,
                            data: (frm.doc.operations || []).map(row => ({
                                operation_row_name: row.name,
                                operation: row.operation,
                                workstation_type: row.workstation_type,
                                workstation: row.workstation,
                                sequence_id: row.sequence_id,
                                description: row.description,
                                time_in_mins: row.time_in_mins,
                                batch_size: row.batch_size
                            })),
                            fields: [
                                {
                                    fieldname: 'operation_row_name',
                                    fieldtype: 'Data',
                                    hidden: 1
                                },
                                {
                                    label: __('Operation'),
                                    fieldname: 'operation',
                                    fieldtype: 'Link',
                                    options: 'Operation',
                                    in_list_view: 1,
                                    columns: 2,
                                    reqd: 1,
                                    async onchange() {
                                        const row = this.doc;
                                        const operation = row.operation;
                                        const set_workstation = workstation => {
                                            // Dialog table rows are not always registered in
                                            // frappe.model.locals, so update their data directly.
                                            row.workstation = workstation || null;
                                            this.grid_row?.refresh_field('workstation');
                                        };

                                        if (!operation) {
                                            set_workstation(null);
                                            return;
                                        }

                                        const r = await frappe.db.get_value(
                                            'Operation',
                                            operation,
                                            'workstation'
                                        );

                                        // Ignore a stale response if the user changed the operation again.
                                        if (row.operation !== operation) return;

                                        set_workstation(r.message?.workstation);
                                    }
                                },
                                {
                                    label: __('Workstation Type'),
                                    fieldname: 'workstation_type',
                                    fieldtype: 'Link',
                                    options: 'Workstation Type'
                                },
                                {
                                    label: __('Workstation'),
                                    fieldname: 'workstation',
                                    fieldtype: 'Link',
                                    options: 'Workstation',
                                    in_list_view: 1,
                                    columns: 2
                                },
                                {
                                    label: __('Sequence ID'),
                                    fieldname: 'sequence_id',
                                    fieldtype: 'Int',
                                    in_list_view: 1,
                                    columns: 1,
                                    default: 1,
                                    non_negative: 1
                                },
                                {
                                    label: __('Time (mins)'),
                                    fieldname: 'time_in_mins',
                                    fieldtype: 'Float',
                                    in_list_view: 1,
                                    columns: 1,
                                    default: 1,
                                    reqd: 1
                                },
                                {
                                    label: __('Batch Size'),
                                    fieldname: 'batch_size',
                                    fieldtype: 'Float',
                                    default: 1,
                                    non_negative: 1
                                },
                                {
                                    label: __('Operation Description'),
                                    fieldname: 'description',
                                    fieldtype: 'Small Text'
                                }
                            ]
                        }
                    ],
                    primary_action_label: __('Update'),
                    primary_action(values) {
                        frappe.call({
                            method: "cardmasters_app.cardmasters_app.api.work_order.update_work_order_details",
                            args: {
                                docname: frm.doc.name,
                                qty: values.qty,
                                item_specifics: values.custom_item_specifics,
                                particulars: values.custom_particulars,
                                operations: values.operations
                            },
                            callback: function(r) {
                                if (r.message === "Success") {
                                    frappe.show_alert({message: __('Details Updated'), indicator: 'green'});
                                    frm.reload_doc();
                                    d.hide();
                                }
                            }
                        });
                    }
                });
                d.show();
            }, __('Options'));

            frm.change_custom_button_type(__('Update Details'), null, 'primary');
        }

		add_workstation_completion_button(frm);
		add_make_to_stock_button(frm);
		show_linked_stock_work_orders(frm);
	},
});

var is_work_order_button = function(label, expected) {
	return label === expected || label === __(expected);
};

var is_work_order_button_group = function(group, expected) {
	return group === expected || group === __(expected);
};

var has_work_order_status_action_permissions = function(frm) {
	return frm.has_perm('write') && frm.has_perm('cancel') && frm.has_perm('delete');
};

var cardmasters_job_cards_disabled = function() {
	const settings = frappe.boot.cardmasters_settings || {};
	return Boolean(Number(settings.disable_job_cards || 0));
};

var filter_work_order_make_buttons = function(frm) {
	if (!frm.custom_make_buttons) {
		return;
	}

	delete frm.custom_make_buttons['Pick List'];

	if (cardmasters_job_cards_disabled() || !frappe.model.can_create('Job Card')) {
		delete frm.custom_make_buttons['Job Card'];
	}

	if (!frm.has_perm('read') || !frappe.model.can_create('Stock Entry')) {
		delete frm.custom_make_buttons['Stock Entry'];
	}
};

var add_make_to_stock_button = function(frm) {
	if (
		frm.is_new() ||
		frm.doc.docstatus === 2 ||
		!frm.doc.sales_order ||
		!frappe.model.can_create('Work Order')
	) {
		return;
	}

	frm.add_custom_button(__('Make to Stock'), function() {
		frm.copy_doc(function(new_work_order) {
			new_work_order.production_item = null;
			new_work_order.item_name = null;
			new_work_order.bom_no = null;
			new_work_order.qty = null;
			new_work_order.custom_customer = null;
			new_work_order.sales_order = null;
			new_work_order.sales_order_item = null;
			new_work_order.custom_parent_work_order = frm.doc.name;
		});
	}, __('Link WO'));
};

var show_linked_stock_work_orders = function(frm) {
	if (frm.is_new() || !frm.doc.sales_order) {
		return;
	}

	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.work_order.get_linked_stock_work_orders',
		args: {docname: frm.doc.name},
		callback: function(r) {
			const work_orders = r.message || [];
			if (!work_orders.length) {
				return;
			}

			const settings = frappe.boot.cardmasters_settings || {};
			const concluded_states = (settings.wo_finished_items_workflow_state || [])
				.map(row => row.workflow_state);
			const in_production_status = settings.wo_in_production_status || 'In Production';
			const in_claiming_status = settings.wo_in_claiming_status || 'In Claiming';

			const rows = work_orders.map(function(work_order) {
				const route = frappe.utils.get_form_link('Work Order', work_order.name);
				let production_status = frappe.utils.escape_html(work_order.workflow_state || '');
				if (concluded_states.includes(work_order.workflow_state)) {
					production_status = `<span class="status-concluded">${__('Production Concluded')}</span>`;
				} else if (work_order.workflow_state === in_production_status) {
					production_status = frappe.utils.escape_html(in_production_status);
				}

				const consumption_status = work_order.status === 'Completed'
					? __('Consumption entry submitted')
					: __('No consumption entry submitted');
				let claiming_status = __('Not In Claiming');
				if (Number(work_order.custom_bypass) === 1) {
					claiming_status = __('{0} (Bypassed)', [in_claiming_status]);
				} else if (work_order.workflow_state === in_claiming_status) {
					claiming_status = in_claiming_status;
				}

				return `<tr>
					<td><a href="${route}" target="_blank"><b>${frappe.utils.escape_html(work_order.name)}</b></a></td>
					<td>${frappe.utils.escape_html(work_order.item_name || '')}</td>
					<td>${format_number(work_order.qty || 0)}</td>
					<td>${frappe.utils.escape_html(work_order.custom_item_specifics || '')}</td>
					<td>${frappe.utils.escape_html(work_order.custom_particulars || '')}</td>
					<td>${production_status}</td>
					<td>${frappe.utils.escape_html(consumption_status)}</td>
					<td>${frappe.utils.escape_html(claiming_status)}</td>
				</tr>`;
			}).join('');

			frm.dashboard.add_section(
				`<style>
					.custom-wo-table { table-layout: fixed; width: 100%; border-collapse: collapse; }
					.custom-wo-table td, .custom-wo-table th {
						white-space: normal !important;
						word-wrap: break-word;
						vertical-align: top;
						padding: 10px 8px;
						font-size: 0.9em;
						border-bottom: 1px solid var(--border-color);
					}
					.status-concluded { color: var(--green-600, #28a745); font-weight: bold; }
				</style>
				<table class="table table-bordered custom-wo-table">
					<thead><tr>
						<th style="width: 12%;">${__('Work Order')}</th>
						<th style="width: 12%;">${__('Item')}</th>
						<th style="width: 6%;">${__('Qty')}</th>
						<th style="width: 13%;">${__('Specifics')}</th>
						<th style="width: 13%;">${__('Particulars')}</th>
						<th style="width: 14%;">${__('Production Status')}</th>
						<th style="width: 15%;">${__('Consumption')}</th>
						<th style="width: 15%;">${__('Claiming Status')}</th>
					</tr></thead>
					<tbody>${rows}</tbody>
				</table>`,
				__('Linked Make-to-Stock Work Orders')
			);
		}
	});
};

var add_workstation_completion_button = function(frm) {
	if (frm.doc.docstatus !== 1) {
		return;
	}

	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.work_order.get_workstation_completion_options',
		args: {
			docname: frm.doc.name
		},
		callback: function(r) {
			const result = r.message || {};

			if (!result.can_show) {
				return;
			}

			add_workstation_completion_action_buttons(frm, result);
		}
	});
};

var add_workstation_completion_action_buttons = function(frm, options) {
	if (options.can_complete && !frm.custom_buttons[__('Mark Workstation Jobs Complete')]) {
		frm.add_custom_button(__('Mark Workstation Jobs Complete'), function() {
			mark_workstation_jobs_complete(frm);
		}, __('Jobs'));
	}

	if (options.can_undo && !frm.custom_buttons[__('Undo Workstation Jobs Complete')]) {
		frm.add_custom_button(__('Undo Workstation Jobs Complete'), function() {
			undo_workstation_jobs_complete(frm);
		}, __('Jobs'));
	}
};

var mark_workstation_jobs_complete = function(frm) {
	select_workstation_for_completion_action(frm, 'complete', confirm_mark_workstation_jobs_complete);
};

var undo_workstation_jobs_complete = function(frm) {
	select_workstation_for_completion_action(frm, 'undo', confirm_undo_workstation_jobs_complete);
};

var select_workstation_for_completion_action = function(frm, action, confirmation_handler) {
	frappe.call({
		method: 'cardmasters_app.cardmasters_app.api.work_order.get_workstation_completion_options',
		args: {
			docname: frm.doc.name,
			action: action
		},
		freeze: true,
		freeze_message: __('Checking workstation assignments...'),
		callback: function(r) {
			const result = r.message || {};
			const workstations = result.workstations || [];

			if (!result.can_show) {
				if (result.message) {
					frappe.msgprint(__(result.message));
				}
				return;
			}

			if (!result.prompt_required && workstations.length === 1) {
				confirmation_handler(frm, workstations[0]);
				return;
			}

			show_workstation_selection_dialog(frm, workstations, confirmation_handler);
		}
	});
};

var show_workstation_selection_dialog = function(frm, workstations, confirmation_handler) {
	let d = new frappe.ui.Dialog({
		title: __('Select Workstation'),
		fields: [
			{
				label: __('Workstation'),
				fieldname: 'workstation',
				fieldtype: 'Select',
				options: workstations.join('\n'),
				reqd: 1
			}
		],
		primary_action_label: __('Select'),
		primary_action(values) {
			d.hide();
			confirmation_handler(frm, values.workstation);
		}
	});

	d.show();
};

var confirm_undo_workstation_jobs_complete = function(frm, workstation) {
	let escaped_workstation = frappe.utils.escape_html(workstation);
	let d = new frappe.ui.Dialog({
		title: __('Confirm'),
		fields: [
			{
				fieldtype: 'HTML',
				options: `
					<p>${__('Undo completion for all responsibilities for {0}?', [escaped_workstation])}</p>
					<p>${__('This will show this Work Order again in the selected workstation queue.')}</p>
				`
			}
		],
		primary_action_label: __('Confirm'),
		primary_action() {
			d.hide();
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.work_order.undo_workstation_jobs_complete',
				args: {
					docname: frm.doc.name,
					workstation: workstation
				},
				freeze: true,
				freeze_message: __('Undoing workstation jobs complete...'),
				callback: function(r) {
					const result = r.message || {};

					if (!result.updated_count) {
						frappe.msgprint(__('No operations found for the selected workstation.'));
						return;
					}

					frm.reload_doc().then(() => {
						frappe.msgprint(__('{0} operation(s) for {1} restored to workstation queue.', [
							result.updated_count,
							result.workstation || workstation
						]));
					});
				}
			});
		},
		secondary_action_label: __('Cancel'),
		secondary_action() {
			d.hide();
		}
	});

	d.show();
};

var confirm_mark_workstation_jobs_complete = function(frm, workstation) {
	let escaped_workstation = frappe.utils.escape_html(workstation);
	let d = new frappe.ui.Dialog({
		title: __('Confirm'),
		fields: [
			{
				fieldtype: 'HTML',
				options: `
					<p>${__('Mark all responsibilities for {0} as complete?', [escaped_workstation])}</p>
					<p>${__('This will hide this Work Order from the selected workstation queue.')}</p>
				`
			}
		],
		primary_action_label: __('Confirm'),
		primary_action() {
			d.hide();
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.work_order.mark_workstation_jobs_complete',
				args: {
					docname: frm.doc.name,
					workstation: workstation
				},
				freeze: true,
				freeze_message: __('Marking workstation jobs complete...'),
				callback: function(r) {
					const result = r.message || {};

					if (!result.updated_count) {
						frappe.msgprint(__('No operations found for the selected workstation.'));
						return;
					}

					frm.reload_doc().then(() => {
						frappe.msgprint(__('{0} operation(s) for {1} marked complete.', [
							result.updated_count,
							result.workstation || workstation
						]));
					});
				}
			});
		},
		secondary_action_label: __('Cancel'),
		secondary_action() {
			d.hide();
		}
	});

	d.show();
};

frappe.ui.form.on('CM Jobs', {
	job: function(frm, cdt, cdn) { 
		update_wo_installation(frm);
	},
	custom_cm_jobs_add: function(frm) {
		update_wo_installation(frm);
	}
});

var update_wo_installation = function(frm) {
	let is_installation = false;

	(frm.doc.custom_cm_jobs || []).forEach(row => {
		if (row.job === 'INSTALLATION') {
			is_installation = true;
		}
	});

	if (is_installation) {
		frm.set_value('custom_installation', 'For Installation');
	} else {
		frm.set_value('custom_installation', 'No Installation'); 
	}
};
