frappe.ui.form.on('Salary Slip', {
    refresh: function(frm) {
        // Run the hide/show logic on load
        handle_submit_button(frm);

        // Listen for ANY edit on the form
        // If user types in any input, force the button to show (so they can Save)
        if (!frm._input_listener_attached) {
            $(frm.wrapper).on('change input', 'input, select, textarea', function() {
                // User is typing -> Form is dirty -> Show the Save button
                frm.page.btn_primary.show();
            });
            frm._input_listener_attached = true;
        }
    }
});

function handle_submit_button(frm) {
    if (frm.doc.docstatus === 0 && !frm.is_dirty()) {
        if (frm.doc.net_pay <= 0) {
            frm.page.btn_primary.hide(); // Hide if condition fails
        } else {
            frm.page.btn_primary.show();
        }
    }
}