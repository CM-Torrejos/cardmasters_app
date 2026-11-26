frappe.ui.form.on('Employee', {
    refresh(frm) {
        // Only show on saved Employee records and for users allowed to create Employee Documents
        if (!frm.is_new() && frappe.model.can_create('Employee Document')) {
            frm.add_custom_button(__('Employee Document'), () => {
                // Pre-fill the Employee field and open the Quick Entry popup
                frappe.route_options = {
                    employee: frm.doc.name
                };
                frappe.new_doc('Employee Document');
            }, __('Create'));
        }
    }
});