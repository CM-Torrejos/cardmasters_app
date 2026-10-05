frappe.ui.form.on('Journal Entry', {
    custom_branch: function(frm) {
        erpnext.utils.copy_value_in_all_rows(
            frm.doc, 
            frm.doc.doctype, 
            frm.doc.name, 
            "accounts",         // The child table fieldname
            "custom_branch",    // Parent field to read from
            "branch"            // Child field to write to
        );
    }
});

frappe.ui.form.on('Journal Entry Account', {
    accounts_add: function(frm, cdt, cdn) {
        if (frm.doc.custom_branch) {
            frappe.model.set_value(cdt, cdn, 'branch', frm.doc.custom_branch);
        }
    }
});