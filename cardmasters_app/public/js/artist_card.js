frappe.ui.form.on('Artist Card', {
	refresh: function(frm) {
		if (frm.doc.sales_order) {
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
						
						frm.fields_dict.sales_order_print.$wrapper.empty().append(iframe);
						
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
		// Only in Layouting state on saved docs
		if (frm.doc.workflow_state === "Layouting" && !frm.is_new()) {
			
			// 1) If no time entries yet, show Start
			if (!frm.doc.timesheet.length) {
				frm.add_custom_button('Start', () => {
					const now = frappe.datetime.now_datetime();
					const row = frm.add_child('timesheet');
					row.from_time = now;
					frm.save().then(() => update_total_time(frm));
				}).addClass('btn-primary');
			}
			
			// look at the last timesheet row
			const last = frm.doc.timesheet.slice(-1)[0];
			
			// 2) If there’s an open interval (started but not paused)
			if (last && last.from_time && !last.to_time) {
				frm.add_custom_button('Pause', () => {
					const now = frappe.datetime.now_datetime();
					// set end time
					frappe.model.set_value(last.doctype, last.name, 'to_time', now);
					// calc minutes
					const mins = moment.duration(
						moment(now).diff(moment(last.from_time))
					).asMinutes();
					frappe.model.set_value(last.doctype, last.name, 'time_in_minutes', mins);
					frm.save().then(() => update_total_time(frm));
				}).addClass('btn-danger');  // ← red button now
				
				// 3) If last entry is closed, allow Resume
			} else if (last && last.to_time) {
				frm.add_custom_button('Resume', () => {
					const now = frappe.datetime.now_datetime();
					const row = frm.add_child('timesheet');
					row.from_time = now;
					frm.save().then(() => update_total_time(frm));
				}).addClass('btn-success');
			}
			
		}
	}
});

// Recalculate the total on the parent
function update_total_time(frm) {
	const total = frm.doc.timesheet
	.reduce((sum, r) => sum + (r.time_in_minutes || 0), 0);
	
	frm.set_value('finished_total_time', total);
	return frm.save();
}
