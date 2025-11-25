frappe.ui.form.on('Work Order', {
    onload: function(frm) {
        if (frm.is_new()) {
            frappe.call({
                method: "cardmasters_app.cardmasters_app.event_handlers.work_order_fdr.skip_material_transfer.get_user_role_profile_settings",
                callback: function(r) {
                    if (r.message && r.message.check_box) {
                        frm.set_value('skip_transfer', 1);
                    }
                }
            });
        }
    }
});