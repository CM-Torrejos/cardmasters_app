// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.ui.form.on('Damages and Returns', {
    setup: function(frm) {
        // Fetch departments based on workstations
        frm.add_fetch('workstation', 'custom_department', 'department');
        frm.add_fetch('workstation_detected', 'custom_department', 'department_detected');

        // Apply a filter to the Damage Reason link field
        frm.set_query('reason_for_damage', function() {
            // Check if error_type is already selected
            if (frm.doc.error_type) {
                return {
                    filters: {
                        // 'Target Field in Damage Reason' : 'Value from this form'
                        'error_type': frm.doc.error_type
                    }
                };
            } else {
                // Optional: Return a filter that guarantees no results if error_type isn't selected yet,
                // forcing the user to select an error_type first.
                return {
                    filters: {
                        'name': ['=', ''] 
                    }
                };
            }
        });
    },

    // When error_type is changed, clear the existing reason_for_damage so 
    // the user doesn't accidentally keep a mismatched reason.
    error_type: function(frm) {
        frm.set_value('reason_for_damage', '');
    }
});