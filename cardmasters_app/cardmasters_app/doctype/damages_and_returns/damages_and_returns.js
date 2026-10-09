// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.ui.form.on('Damages and Returns', {
    setup: function(frm) {
        // Syntax: frm.add_fetch(link_fieldname, source_fieldname, target_fieldname)
        frm.add_fetch('workstation', 'custom_department', 'department');
        frm.add_fetch('workstation_detected', 'custom_department', 'department_detected');
    }
});