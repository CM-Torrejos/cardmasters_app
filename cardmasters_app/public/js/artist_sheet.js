frappe.ui.form.on('Artist Sheet', {
	refresh: function(frm) {
    	// Only show buttons if the workflow_state is "Layouting"
    	if (frm.doc.workflow_state === "Layouting" && !frm.is_new()) {
        	if (!frm.doc.timesheet.length) {
            	frm.add_custom_button('Start', function() {
                	let now = frappe.datetime.now_datetime();
                	let row = frm.add_child('timesheet');
                	row.from_time = now;
                	frm.save();
            	}).addClass('btn-primary');
        	}

        	let last_row = frm.doc.timesheet.slice(-1)[0];

        	// If the last row is incomplete (paused or started but not completed)
        	if (last_row && last_row.from_time && !last_row.to_time) {
            	frm.add_custom_button('Pause', function() {
                	let now = frappe.datetime.now_datetime();
                	frappe.model.set_value(last_row.doctype, last_row.name, 'to_time', now);

                	// Calculate duration
                	let start = moment(last_row.from_time);
                	let end = moment(now);
                	let duration = moment.duration(end.diff(start)).asMinutes();

                	frappe.model.set_value(last_row.doctype, last_row.name, 'time_in_minutes', duration);
                	frm.save().then(() => {
                    	update_total_time(frm);
                	});
            	}).addClass('btn-warning');

            	// Complete the task
            	frm.add_custom_button('Complete', function() {
                	frappe.confirm(
                    	'Are you sure you want to mark this task as completed?',
                    	function() {
                        	let now = frappe.datetime.now_datetime();
                        	frappe.model.set_value(last_row.doctype, last_row.name, 'to_time', now);

                        	// Calculate total time for last row
                        	let start = moment(last_row.from_time);
                        	let end = moment(now);
                        	let duration = moment.duration(end.diff(start)).asMinutes();
                        	frappe.model.set_value(last_row.doctype, last_row.name, 'time_in_minutes', duration);

                        	// Set status to Closed and refresh form
                       	 
                    	}
                	);
            	}).addClass('btn-danger');
        	} else if (last_row && last_row.to_time) {
            	// If the last entry is complete, allow for resumption of work
            	frm.add_custom_button('Resume', function() {
                	let now = frappe.datetime.now_datetime();
                	let row = frm.add_child('timesheet');
                	row.from_time = now;
                	frm.save().then(() => {
                    	update_total_time(frm); // Recalculate time after resuming
                	});
            	}).addClass('btn-success');
        	}
    	}
	}
});

// Function to calculate the total time spent (sum of all time_in_minutes in the child table)
function update_total_time(frm) {
	let total_time = 0;
	frm.doc.timesheet.forEach(function(row) {
    	if (row.time_in_minutes) {
        	total_time += row.time_in_minutes;
    	}
	});
	// Update the total_time_in_minutes field in the parent Artist Sheet doctype
	frm.set_value('total_time_in_minutes', total_time);
	frm.save(); // Save the updated total time
}
