frappe.ui.form.on('Job Card', {
    refresh: function(frm) {
        // Wait 100ms to ensure the standard script has finished rendering buttons
        setTimeout(() => {
            // Attempt to find the standard "Start Job" button
            // Search for the button object to ensure it actually exists before replacing it
            if (frm.custom_buttons && frm.custom_buttons['Start Job']) {
                
                // 1. Remove the Standard Button
                frm.remove_custom_button('Start Job');

                // 2. Add Custom "Start Job" Button
                frm.add_custom_button(__('Start Job'), function() {
                    
                    // 3. Call the core 'start_job' function directly
                    // Passing [] as the employee list skips the dialog
                    if (frm.events.start_job) {
                         frm.events.start_job(frm, "Work In Progress", []);
                    } else {
                        frappe.msgprint(__("Standard Job Card events are not loaded."));
                    }

                }).addClass('btn-primary');
            }
        }, 100);
    }
});