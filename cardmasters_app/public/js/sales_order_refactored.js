(function() {
	// For Project Automation
	let PROJECT_AUTOMATION_DISABLED = 0;
	let PROJECT_THRESHOLD = 100000; 
	let PROJECT_ITEMS = [];
	
	// For Color Mapping for Custom Pill
	let WORKFLOW_COLOR_MAP = {};
	
	// For Custom Work Order Pill
	let WO_CONCLUDED_STATES = [];
	let WO_DRAFT_STATUS = 'Draft';
	let WO_NOT_STARTED_STATUS = 'Not Started';
	let WO_IN_PRODUCTION_STATUS = 'In Production';
	let WO_IN_CLAIMING_STATUS = 'In Claiming';
	
	frappe.ui.form.on('Sales Order', {
		setup: function(frm) {
			
			// 1. Access the bootinfo dictionary synchronously
			let settings = frappe.boot.cardmasters_settings;
			
			if (settings) {
				// 2. Hydrate Kill Switch
				PROJECT_AUTOMATION_DISABLED = settings.project_automation_disabled || 0;
				
				// 3. Hydrate Magic Number
				if (settings.item_price_threshold) {
					PROJECT_THRESHOLD = settings.item_price_threshold;
				}
				
				// 4. Populate Child Table Items
				if (settings.project_items_table) {
					PROJECT_ITEMS = settings.project_items_table.map(row => row.item_code);
				}
				
				// 5. Build the Custom Pill Color Map dynamically
				if (settings.workflow_state_color_matrix) {
					settings.workflow_state_color_matrix.forEach(row => {
						if (row.workflow_state && row.color) {
							let formatted_color = row.color.toLowerCase().replace(/\s+/g, '-');
							WORKFLOW_COLOR_MAP[row.workflow_state] = formatted_color; 
						}
					});
				}
				
				// 6. Hydrate Work Order Statuses
				if (settings.wo_finished_items_workflow_state) {
					WO_CONCLUDED_STATES = settings.wo_finished_items_workflow_state.map(row => row.workflow_state);
				}
				if (settings.wo_draft_status) { WO_DRAFT_STATUS = settings.wo_draft_status; }
				if (settings.wo_not_started_status) { WO_NOT_STARTED_STATUS = settings.wo_not_started_status; }
				if (settings.wo_in_production_status) { WO_IN_PRODUCTION_STATUS = settings.wo_in_production_status; }
				if (settings.wo_in_claiming_status) { WO_IN_CLAIMING_STATUS = settings.wo_in_claiming_status; }
			}
		},

		onload: function(frm) {
			set_branch_from_current_user_employee(frm);
		},
		
		refresh: function(frm) {
			const invalid_statuses = ['On Hold', 'Cancelled', 'Closed', 'Draft'];
			set_branch_from_current_user_employee(frm);
			
			// Set Secondary Status Pill
			set_custom_pill(frm);
			
			// Render Work Order Progress HTML block
			render_wo_html_block(frm);
			
			// Set Update Items Button
			if (frappe.model.can_write("Sales Order")) {
				set_update_items_button(frm);
			}
			
			// Set Complaint, Quotation, and Credit Memo
			if (!frm.is_new() && !invalid_statuses.includes(frm.doc.status)) {
				if (frappe.model.can_create('Stock Entry')) {
					set_batched_material_transfer_button(frm);
				}
				// Artist card button can only be seen by the user with access
				if (frappe.model.can_create("Artist Card")) {
					set_artist_card_button(frm, invalid_statuses);
				}
				set_complaint_button(frm);
				set_credit_memo_button(frm);
				set_quotation_button(frm);
			}
			
			// Render Outstanding balance
			render_outstanding_balance(frm)

			// Render the customer's company-specific dashboard balance
			render_customer_total_unpaid(frm);
			render_customer_sales_order_outstanding(frm);
			
			// Validation check (may no longer be needed since specifics and particulars cna only be updated in update items now)
			// validate_discrepancy_against_wo(frm)
		},
		
		workflow_state: function(frm) {
			// This supposedly listen to changes to the status
			set_custom_pill(frm);
		},
		
		// Sales Channels
		custom_sales_channel: function(frm){
			validate_sales_partner(frm);
		},

		customer: function(frm) {
			render_customer_total_unpaid(frm);
			render_customer_sales_order_outstanding(frm);
		},

		company: function(frm) {
			render_customer_total_unpaid(frm);
			render_customer_sales_order_outstanding(frm);
		},
		
		// Grant stuff
		custom_grant: function(frm) {
			set_grant(frm);
		},
		
		// Declare lost
		before_workflow_action: (frm) => {
			return set_declare_lost_button(frm); 
		},
		
		// Project Validation
		validate: function(frm) {
			// If a project is already linked, proceed with save normally
			validate_project(frm);
		}
	});

	function set_branch_from_current_user_employee(frm) {
		if (!frm.is_new() || frm.doc.branch || frm.__setting_employee_branch) {
			return;
		}

		frm.__setting_employee_branch = true;
		frappe.call({
			method: 'cardmasters_app.cardmasters_app.api.sales_order.get_current_user_employee_branch',
			callback: function(r) {
				if (r.message && !frm.doc.branch) {
					frm.set_value('branch', r.message);
				}
			},
			always: function() {
				frm.__setting_employee_branch = false;
			}
		});
	}

	function set_batched_material_transfer_button(frm) {
		frm.add_custom_button(__('Batched Material Transfer'), function() {
			frappe.model.open_mapped_doc({
				method: 'cardmasters_app.cardmasters_app.api.sales_order.make_batched_material_transfer',
				frm: frm
			});
		}, __('Create'));
	}
	
	function set_custom_pill(frm) {
		// 1. SCOPE TO CURRENT FORM: This prevents the pill from bleeding into other pages
		const $wrapper = frm.page.wrapper;
		
		// 2. Remove existing custom pill (within this wrapper only) to prevent duplicates
		$wrapper.find('.custom-state-pill').remove();
		
		const state = frm.doc.workflow_state; 
		if (!state) {
			return;
		}
		
		// No more hardcoding. We pull straight from the database mapping.
		// If the state isn't in the settings, it defaults to 'gray'
		const color = WORKFLOW_COLOR_MAP[state] || 'gray';
		
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
	
	function set_update_items_button(frm) {
		
		let settings = frappe.boot.cardmasters_settings;
		
		// 2. Check the kill switch: If disabled, exit the function immediately
		if (settings && settings.item_details_validation_disabled) {
			return; 
		}
		
		if (frm.doc.docstatus === 1) {
			
			// 1. Remove the standard core button so users can't click it
			frm.remove_custom_button('Update Items'); 
			
			// 2. Add your own button with the exact same name
			frm.add_custom_button('Update Items', () => {
				
				// --- NO MORE 'opts' --- 
				// We hardcode the Sales Order specific parameters instead
				const cannot_add_row = false;
				const child_docname = "items";
				const child_meta = frappe.get_meta(`${frm.doc.doctype} Item`);
				
				// Manually check if any item has reserved stock 
				const has_reserved_stock = frm.doc.items.some(d => d.stock_reserved_qty > 0);
				
				// Optional chaining (?.) prevents errors if precision isn't found
				const get_precision = (fieldname) => child_meta.fields.find((f) => f.fieldname == fieldname)?.precision;
				
				// Store mapped data in a local variable instead of "this.data"
				let dialog_data = frm.doc.items.map((d) => {
					return {
						docname: d.name,
						name: d.name,
						item_code: d.item_code,
						delivery_date: d.delivery_date,
						schedule_date: d.schedule_date,
						conversion_factor: d.conversion_factor,
						qty: d.qty,
						rate: d.rate,
						uom: d.uom,
						fg_item: d.fg_item,
						fg_item_qty: d.fg_item_qty,
						custom_item_specifics: d.custom_item_specifics,
						custom_particulars: d.custom_particulars
					};
				});
				
				const fields = [
					{ fieldtype: "Data", fieldname: "docname", read_only: 1, hidden: 1 },
					{
						fieldtype: "Link",
						fieldname: "item_code",
						options: "Item",
						in_list_view: 1,
						read_only: 0,
						disabled: 0,
						label: __("Item Code"),
						get_query: function () {
							return { query: "erpnext.controllers.queries.item_query", filters: { is_sales_item: 1 } };
						},
						onchange: function () {
							const me = this;
							frm.call({
								method: "erpnext.stock.get_item_details.get_item_details",
								args: {
									doc: frm.doc,
									args: {
										item_code: this.value,
										set_warehouse: frm.doc.set_warehouse,
										customer: frm.doc.customer || frm.doc.party_name,
										currency: frm.doc.currency,
										conversion_rate: frm.doc.conversion_rate,
										price_list: frm.doc.selling_price_list,
										price_list_currency: frm.doc.price_list_currency,
										plc_conversion_rate: frm.doc.plc_conversion_rate,
										company: frm.doc.company,
										order_type: frm.doc.order_type,
										is_pos: cint(frm.doc.is_pos),
										ignore_pricing_rule: frm.doc.ignore_pricing_rule,
										doctype: frm.doc.doctype,
										name: frm.doc.name,
										qty: me.doc.qty || 1,
										uom: me.doc.uom,
										pos_profile: cint(frm.doc.is_pos) ? frm.doc.pos_profile : "",
										tax_category: frm.doc.tax_category,
										child_doctype: frm.doc.doctype + " Item",
									},
								},
								callback: function (r) {
									if (r.message) {
										const { qty, price_list_rate: rate, uom, conversion_factor, bom_no } = r.message;
										const row = dialog.fields_dict.trans_items.df.data.find((doc) => doc.idx == me.doc.idx);
										if (row) {
											Object.assign(row, {
												conversion_factor: me.doc.conversion_factor || conversion_factor,
												uom: me.doc.uom || uom,
												qty: me.doc.qty || qty,
												rate: me.doc.rate || rate,
												bom_no: bom_no,
											});
											dialog.fields_dict.trans_items.grid.refresh();
										}
									}
								},
							});
						},
					},
					{
						fieldtype: "Link",
						fieldname: "uom",
						options: "UOM",
						read_only: 0,
						label: __("UOM"),
						reqd: 1,
						onchange: function () {
							frappe.call({
								method: "erpnext.stock.get_item_details.get_conversion_factor",
								args: { item_code: this.doc.item_code, uom: this.value },
								callback: (r) => {
									if (!r.exc) {
										if (this.doc.conversion_factor == r.message.conversion_factor) return;
										const docname = this.doc.docname;
										dialog.fields_dict.trans_items.df.data.some((doc) => {
											if (doc.docname == docname) {
												doc.conversion_factor = r.message.conversion_factor;
												dialog.fields_dict.trans_items.grid.refresh();
												return true;
											}
										});
									}
								},
							});
						},
					},
					{ fieldtype: "Date", fieldname: "delivery_date", in_list_view: 1, label: __("Delivery Date"), reqd: 1 },
					{ fieldtype: "Float", fieldname: "conversion_factor", label: __("Conversion Factor"), precision: get_precision("conversion_factor") },
					{ fieldtype: "Float", fieldname: "qty", default: 0, read_only: 0, in_list_view: 1, label: __("Qty"), precision: get_precision("qty") },
					{ fieldtype: "Currency", fieldname: "rate", options: "currency", default: 0, read_only: 0, in_list_view: 1, label: __("Rate"), precision: get_precision("rate") },
					{ fieldtype: "Small Text", fieldname: "custom_item_specifics", in_list_view: 1, label: __("Item Specifics") },
					{ fieldtype: "Text", fieldname: "custom_particulars", in_list_view: 1, label: __("Particulars") },
				];
				
				let dialog = new frappe.ui.Dialog({
					title: __("Update Items"),
					size: "extra-large",
					fields: [
						{ fieldname: "trans_items", fieldtype: "Table", label: "Items", cannot_add_rows: cannot_add_row, in_place_edit: false, reqd: 1, data: dialog_data, get_data: () => { return dialog_data; }, fields: fields }
					],
					primary_action: function () {
						if (has_reserved_stock) {
							this.hide();
							frappe.confirm(
								__("The reserved stock will be released when you update items. Are you certain you wish to proceed?"),
								() => this.update_items(),
								() => this.show() 
							);
						} else {
							this.update_items();
						}
					},
					
					update_items: function () {
						// const trans_items = this.get_values()["trans_items"].filter((item) => !!item.item_code);
						
						const trans_items = this.get_values()["trans_items"]
						.filter((item) => !!item.item_code)
						.map((item) => {
							// Strip leading and trailing whitespace exactly like your Python script does
							if (item.custom_item_specifics) {
								item.custom_item_specifics = String(item.custom_item_specifics).trim();
							}
							if (item.custom_particulars) {
								item.custom_particulars = String(item.custom_particulars).trim();
							}
							item.price_list_rate = item.rate;
							return item;
						});
						// PHASE 3: Define final execution API (Helper Function)
						const proceed_with_update = (project_name = null) => {
							frappe.call({
								method: "cardmasters_app.cardmasters_app.api.sales_order.update_custom_child_fields",
								freeze: true,
								args: {
									parent_doctype: frm.doc.doctype,
									trans_items: trans_items,
									parent_doctype_name: frm.doc.name,
									child_docname: child_docname,
									new_project_name: project_name 
								},
								callback: function () {
									frm.reload_doc();
								},
							});
							this.hide();
							refresh_field("items");
						};
						
						// PHASE 2: Define Project Check Logic (Helper Function)
						const check_project_and_proceed = () => {
							if (!frm.doc.project) {
								let needs_project = trans_items.some(item => item_requires_project(item, frm));
								
								if (needs_project) {
									let project_prompt = frappe.prompt([
										{ fieldtype: 'HTML', fieldname: 'instruction_message', options: '<div style="margin-bottom: 15px; font-size: 13px; color: var(--text-muted);">Updating this Sales Order introduces high-value items (100K+) or project-specific items.<br><br><b>A Project is required to proceed.</b> Please enter a unique name below to automatically create and link the project.</div>' },
										{ label: 'Project Name', fieldname: 'project_name', fieldtype: 'Data', reqd: 1 }
									], function(values) {
										frappe.call({
											method: "cardmasters_app.cardmasters_app.api.sales_order.create_project_for_sales_order",
											args: { project_name: values.project_name },
											callback: function(r) {
												if (r.message) {
													frappe.hide_progress();
													frappe.show_alert({message: `Project ${r.message} created and will be linked.`, indicator: 'green'});
													proceed_with_update(r.message);
												} else {
													frappe.hide_progress();
												}
											},
											error: () => frappe.hide_progress()
										});
									}, 'Project Required', 'Create & Update');
									
									// 🎨 Phase 2 Polish: Gray out background behind Project prompt
									project_prompt.$wrapper.css('background-color', 'rgba(30, 30, 30, 0.75)');
									return; 
								}
							}
							proceed_with_update();
						};
						
						// PHASE 1: Execution starts here! Check WO Discrepancy first.
						frappe.call({
							method: "cardmasters_app.cardmasters_app.api.sales_order.check_wo_discrepancy",
							freeze: true,
							freeze_message: "Checking for Work Order discrepancies...",
							args: {
								so_name: frm.doc.name,
								items: JSON.stringify(trans_items) 
							},
							callback: function(r) {
								if (r.message) {
									// Capture the confirmation object
									let discrepancy_confirm = frappe.confirm(
										r.message,
										function() {
											// User clicked Yes -> Proceed to Phase 2
											check_project_and_proceed();
										},
										function() {
											// User clicked No -> Do nothing
											return;
										}
									);
									
									// 🎨 THE MAGIC LINE: Phase 1 Polish
									discrepancy_confirm.$wrapper.css('background-color', 'rgba(30, 30, 30, 0.75)');
									
								} else {
									// No discrepancy found -> Proceed to Phase 2
									check_project_and_proceed();
								}
							},
							error: function() {
								frappe.msgprint("An error occurred while checking for discrepancies.");
							}
						});
					},
					primary_action_label: __("Update"),
				});
				
				dialog.show();
			});
		}
		
	}
	
	function set_artist_card_button(frm, invalid_statuses) {
		if (!invalid_statuses.includes(frm.doc.status)) {
			frm.add_custom_button(__('Artist Card'), function() {
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
	
	function set_complaint_button(frm) {
		frm.add_custom_button(__('Complaint'), function() {
			frappe.new_doc('Complaint', {
				sales_order: frm.doc.name,
				customer: frm.doc.customer,
			});
		}, __('Create'));
	}
	
	function set_credit_memo_button(frm) {
		frm.add_custom_button(__('Credit Memo'), function() {
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
			}, function(credit_memo) {
				set_credit_memo_sponsored_items(frm, credit_memo);
			});
		}, __('Create'));
	}

	function set_credit_memo_sponsored_items(frm, credit_memo) {
		(credit_memo.sponsored_items_table || []).splice(0);

		(frm.doc.items || []).forEach(function(item) {
			let row = frappe.model.add_child(
				credit_memo,
				'Credit Memo Sponsored Item',
				'sponsored_items_table'
			);

			row.item_code = item.item_code;
			row.particulars = item.custom_particulars || item.description || item.item_name;
			row.quantity = item.qty;
			row.rate = item.rate;
			row.amount = item.amount;
			row.sponsored_rate = item.rate;
			row.sales_order_item = item.name;
		});
	}
	
	function set_quotation_button(frm) {
		frm.add_custom_button(__('Quotation'), function() {
			frappe.model.open_mapped_doc({
				method: "cardmasters_app.cardmasters_app.api.sales_order.make_quotation_from_so",
				frm: frm
			});
		}, __("Create"));
	}
	
	function render_wo_html_block(frm) {
		if (frm.is_new()) {
			return;
		}

		frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Work Order',
				filters: {
					docstatus: ["!=", 2]
				},
				or_filters: [
					['Work Order', 'sales_order', '=', frm.doc.name],
					['Work Order', 'custom_document_id', '=', frm.doc.name]
				],
				fields: ['name', 'workflow_state', 'item_name', 'status', 'qty', 'custom_item_specifics', 'custom_particulars', 'custom_bypass', 'sales_order_item', 'custom_document_id', 'custom_document_item_id', 'custom_production_type'],
				limit: 0
			},
			callback: function(response) {
				const work_orders = response.message || [];
				const standard_work_orders = work_orders.filter(wo => wo.custom_production_type !== 'Backjob');
				const backjob_work_orders = work_orders.filter(wo => {
					return wo.custom_production_type === 'Backjob' && wo.custom_document_id === frm.doc.name;
				});

				load_work_order_withdrawals(work_orders, function(withdrawals_by_work_order) {
					render_work_order_cards(frm, {
						fieldname: 'custom_progress_summary',
						work_orders: standard_work_orders,
						row_link_field: 'sales_order_item',
						withdrawals_by_work_order,
						show_all_items: true,
						empty_message: __('No Work Order created')
					});
					render_backjob_html_block(frm, backjob_work_orders, withdrawals_by_work_order);
				});
			}
		});
	}

	function load_work_order_withdrawals(work_orders, callback) {
		const work_order_names = work_orders.map(wo => wo.name);
		if (!work_order_names.length) {
			callback({});
			return;
		}

		frappe.call({
			method: 'frappe.client.get_list',
			args: {
				doctype: 'Stock Entry',
				filters: {
					work_order: ['in', work_order_names],
					stock_entry_type: 'Material Transfer for Manufacture',
					docstatus: 1
				},
				fields: ['name', 'work_order'],
				order_by: 'posting_date asc, posting_time asc, creation asc',
				limit: 0
			},
			callback: function(response) {
				const grouped = {};
				(response.message || []).forEach(stock_entry => {
					if (!grouped[stock_entry.work_order]) {
						grouped[stock_entry.work_order] = [];
					}
					grouped[stock_entry.work_order].push(stock_entry.name);
				});
				callback(grouped);
			},
			error: function() {
				// Keep the progress UI usable if this user cannot read Stock Entries.
				callback({});
			}
		});
	}

	function render_backjob_html_block(frm, backjob_work_orders, withdrawals_by_work_order) {
		render_work_order_cards(frm, {
			fieldname: 'custom_backjob_summary',
			work_orders: backjob_work_orders,
			row_link_field: 'custom_document_item_id',
			withdrawals_by_work_order,
			show_all_items: false,
			global_empty_message: __('No Backjob Work Orders found.')
		});
	}

	function render_work_order_cards(frm, options) {
		const field = frm.fields_dict[options.fieldname];
		if (!field) return;

		const safe = value => frappe.utils.escape_html(String(value ?? ''));
		const items = options.show_all_items
			? (frm.doc.items || [])
			: (frm.doc.items || []).filter(item => options.work_orders.some(wo => wo[options.row_link_field] === item.name));

		if (!items.length && options.global_empty_message) {
			field.$wrapper.html(`<div class="text-muted wo-global-empty">${options.global_empty_message}</div>`);
			return;
		}

		let html = `${work_order_card_styles()}`;
		items.forEach(so_item => {
			const linked_work_orders = options.work_orders.filter(wo => wo[options.row_link_field] === so_item.name);
			const total_work_order_qty = linked_work_orders.reduce((total, wo) => total + Number(wo.qty || 0), 0);

			html += `
				<section class="so-progress-card">
					<div class="so-progress-card__meta">
						<div class="so-progress-card__row">${__('SO Row #')}: ${safe(so_item.idx)}</div>
						<div class="so-progress-card__item">${__('Item Code')}: ${safe(so_item.item_code)}: ${safe(so_item.item_name)}</div>
						<div class="so-progress-card__particulars"><span>${__('Particulars')}:</span> ${safe(so_item.custom_particulars)}</div>
						<div class="so-progress-card__quantity">${__('Quantity')}: ${safe(so_item.qty)}</div>
					</div>
					<div class="so-progress-card__table-wrap">
						<table class="so-progress-wo-table">
							<thead><tr>
								<th>${__('Work Order')}</th>
								<th class="text-right">${__('Qty')}</th>
								<th>${__('Production Status')}</th>
								<th>${__('Withdrawals')}</th>
								<th>${__('Consumption Status')}</th>
								<th>${__('Delivery Status')}</th>
							</tr></thead><tbody>`;

			linked_work_orders.forEach(wo => {
				const wo_name = safe(wo.name);
				html += `
					<tr>
						<td><a href="/app/work-order/${encodeURIComponent(wo.name)}" target="_blank"><strong>${wo_name}</strong></a></td>
						<td class="text-right">${safe(wo.qty)}</td>
						<td>${get_work_order_production_status(wo, safe)}</td>
						<td>${render_withdrawal_links(options.withdrawals_by_work_order[wo.name] || [], safe)}</td>
						<td>${safe(wo.status === 'Completed' ? __('Consumption entry submitted') : __('No consumption entry submitted'))}</td>
						<td>${safe(get_work_order_delivery_status(wo))}</td>
					</tr>`;
			});

			if (!linked_work_orders.length) {
				html += `<tr class="so-progress-empty"><td colspan="6">${options.empty_message}</td></tr>`;
			} else if (options.show_all_items && Number(so_item.qty || 0) > total_work_order_qty) {
				const remaining_qty = Number(so_item.qty || 0) - total_work_order_qty;
				html += `<tr class="so-progress-empty"><td colspan="6">${__('No Work Order created for remaining quantity')}: ${safe(remaining_qty)}</td></tr>`;
			}

			html += '</tbody></table></div></section>';
		});

		field.$wrapper.html(html);
	}

	function get_work_order_production_status(wo, safe) {
		if (WO_CONCLUDED_STATES.includes(wo.workflow_state)) {
			return `<span class="status-concluded">${__('Production Concluded')}</span>`;
		}
		return safe(wo.workflow_state || '');
	}

	function get_work_order_delivery_status(wo) {
		if (wo.custom_bypass == 1) {
			return `${WO_IN_CLAIMING_STATUS} (${__('Bypassed')})`;
		}
		return wo.workflow_state === WO_IN_CLAIMING_STATUS ? WO_IN_CLAIMING_STATUS : __('Not In Claiming');
	}

	function render_withdrawal_links(stock_entry_names, safe) {
		if (!stock_entry_names.length) return __('None');
		return stock_entry_names.map(name => {
			return `<a class="so-progress-withdrawal" href="/app/stock-entry/${encodeURIComponent(name)}" target="_blank">${safe(name)}</a>`;
		}).join('');
	}

	function work_order_card_styles() {
		return `
			<style>
				.so-progress-card { border: 1px solid var(--border-color); border-radius: var(--border-radius-md, 8px); margin: 0 0 18px; overflow: hidden; background: var(--card-bg, var(--fg-color)); }
				.so-progress-card__meta { padding: 14px 16px; border-bottom: 1px solid var(--border-color); background: var(--subtle-fg, var(--control-bg)); }
				.so-progress-card__meta > div + div { margin-top: 7px; }
				.so-progress-card__row { font-weight: 600; color: var(--text-muted); }
				.so-progress-card__item { font-size: 1.05em; font-weight: 600; color: var(--text-color); }
				.so-progress-card__particulars { white-space: pre-wrap; overflow-wrap: anywhere; color: var(--text-color); }
				.so-progress-card__particulars span, .so-progress-card__quantity { color: var(--text-muted); }
				.so-progress-card__table-wrap { overflow-x: auto; }
				.so-progress-wo-table { width: 100%; min-width: 760px; table-layout: fixed; border-collapse: collapse; margin: 0; }
				.so-progress-wo-table th, .so-progress-wo-table td { padding: 9px 10px; vertical-align: top; text-align: left; white-space: normal; overflow-wrap: anywhere; border-bottom: 1px solid var(--border-color); }
				.so-progress-wo-table th { color: var(--text-muted); background: var(--subtle-fg, var(--control-bg)); font-size: var(--text-xs); font-weight: 600; }
				.so-progress-wo-table th:nth-child(1) { width: 17%; }
				.so-progress-wo-table th:nth-child(2) { width: 7%; }
				.so-progress-wo-table th:nth-child(3) { width: 19%; }
				.so-progress-wo-table th:nth-child(4) { width: 18%; }
				.so-progress-wo-table th:nth-child(5) { width: 21%; }
				.so-progress-wo-table th:nth-child(6) { width: 18%; }
				.so-progress-wo-table tbody tr:last-child td { border-bottom: 0; }
				.so-progress-wo-table .text-right { text-align: right; }
				.so-progress-withdrawal { display: block; width: fit-content; max-width: 100%; }
				.so-progress-withdrawal + .so-progress-withdrawal { margin-top: 3px; }
				.so-progress-empty, .wo-global-empty { color: var(--text-muted); font-style: italic; }
				.wo-global-empty { padding: 12px 0; }
				.status-concluded { color: var(--green-600, #28a745); font-weight: 600; }
				@media (max-width: 767px) {
					.so-progress-card__meta { padding: 12px; }
					.so-progress-wo-table th, .so-progress-wo-table td { padding: 8px; }
				}
			</style>`;
	}
	
	function render_outstanding_balance(frm) {
		if (frm.doc.docstatus === 1) {
			frappe.call({
				method: 'cardmasters_app.cardmasters_app.api.sales_order.get_sales_order_outstanding',
				args: { so_name: frm.doc.name },
				callback: function(r) {
					if (r.message !== undefined && r.message !== frm.doc.custom_outstanding_balance) {
						// Update locally and refresh UI without making the form dirty
						frm.doc.custom_outstanding_balance = r.message;
						frm.refresh_field('custom_outstanding_balance');
					}
				}
			});
		}
	}

	function render_customer_total_unpaid(frm) {
		const field = frm.get_field('custom_total_unpaid');
		if (!field?.$wrapper) return;

		field.$wrapper.empty().css('margin-bottom', '16px');
		if (!frm.doc.customer || !frm.doc.company) return;

		const customer = frm.doc.customer;
		const company = frm.doc.company;

		frappe.call({
			method: 'cardmasters_app.cardmasters_app.api.sales_order.get_customer_dashboard_balance',
			args: { customer, company },
			callback: function(r) {
				if (frm.doc.customer !== customer || frm.doc.company !== company) return;

				const info = r.message;
				if (!info) {
					field.$wrapper.text(__('No customer balance available for this company'));
					return;
				}

				const amount = Number(info.balance_amount) || 0;
				const amount_element = $('<strong>', {
					text: format_currency(amount, info.currency),
				});

				if (amount > 0) {
					amount_element.css('color', 'var(--red-600, #dc3545)');
				}

				field.$wrapper
					.empty()
					.append($('<span>', { text: `${__('Total Unpaid')}: ` }), amount_element);
			}
		});
	}

	function render_customer_sales_order_outstanding(frm) {
		const field = frm.get_field('custom_total_unpaid_sales_orders');
		if (!field?.$wrapper) return;

		field.$wrapper.empty().css('margin-bottom', '16px');
		if (!frm.doc.customer || !frm.doc.company) return;

		const customer = frm.doc.customer;
		const company = frm.doc.company;

		frappe.call({
			method: 'cardmasters_app.cardmasters_app.api.sales_order.get_customer_sales_order_outstanding',
			args: { customer, company },
			callback: function(r) {
				if (frm.doc.customer !== customer || frm.doc.company !== company) return;

				const amount = Number(r.message) || 0;
				const amount_element = $('<strong>', {
					text: format_currency(amount, frm.doc.currency),
				});

				if (amount > 0) {
					amount_element.css('color', 'var(--red-600, #dc3545)');
				}

				field.$wrapper
					.empty()
					.append($('<span>', { text: `${__('Total Unpaid Sales Orders')}: ` }), amount_element);
			}
		});
	}
	
	function validate_discrepancy_against_wo(frm) {
		// This is a monkey-patch for the frm.save. Currently there is no present before update after submit hook frontend.
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
	}
	
	function validate_sales_partner(frm) {
		frappe.call({
			method: "frappe.client.get_value",
			args: {
				doctype: "Sales Channel",
				filters: { name: frm.doc.custom_sales_channel },
				fieldname: "has_sales_partner"
			},
			callback: function(response) {
				if (response.message) {
					let has_sales_partner = response.message.has_sales_partner;
					if (has_sales_partner){
						frm.set_df_property('sales_partner', 'reqd', 1);
					}else{
						frm.set_df_property('sales_partner', 'reqd', 0);
					}
				}
			}
		});
	}
	
	function set_grant(frm) {
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
	
	function set_declare_lost_button(frm) {
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
					// 1. Set value on the form model (does NOT bypass server hooks)
					frm.set_value('custom_lost_reason', values.custom_lost_reason);
					
					// 2. Save the form so the value persists through the proper save lifecycle
					frm.save()
					.then(() => {
						// 3. Resolve the promise to let the workflow finish its transition
						resolve();
					})
					.catch(() => {
						frappe.msgprint(__('Failed to save to database.'));
						reject(); // Stop workflow if the save fails
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
}

	function validate_project(frm) {
		if (frm.doc.project) {
			return;
		}
		
		let needs_project = frm.doc.items && frm.doc.items.some(item => item_requires_project(item, frm));
		
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
					method: "cardmasters_app.cardmasters_app.api.sales_order.create_project_for_sales_order",
					args: {
						project_name: values.project_name
					},
					callback: function(r) {
						frappe.hide_progress();
						if (r.message) {
							// Link the newly created Project to the Sales Order
							frm.set_value('project', r.message);
							frappe.show_alert({message: `Project ${r.message} created and linked.`, indicator: 'green'});
							
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

	// This is a helper function to check items for projects
	function item_requires_project(item, frm) {
		// Called by check_project_and_proceed in set_update_items button, and validate_project function
		
		// 1. If the admin disabled the feature, immediately return false
		if (typeof PROJECT_AUTOMATION_DISABLED !== 'undefined' && PROJECT_AUTOMATION_DISABLED) {
			return false;
		}
		
		// 2. If the item is in the settings child table, immediately return true
		if (typeof PROJECT_ITEMS !== 'undefined' && PROJECT_ITEMS.includes(item.item_code)) {
			return true;
		}
		
		// 3. New logic: Check if the INDIVIDUAL ITEM's amount meets the threshold
		// Using item.amount (which is qty * rate for that specific row)
		let item_amount = item.amount || ((item.qty || 0) * (item.rate || 0)) || 0;
		
		return item_amount >= PROJECT_THRESHOLD;
	}
})();
