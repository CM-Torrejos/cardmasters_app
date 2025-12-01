frappe.ui.form.on('Work Order', {
    refresh: function(frm) {

        if (frm.doc.docstatus === 0 && !frm.doc.__settings_loaded) {
            
            setTimeout(function() {
                frappe.call({
                    method: "cardmasters_app.cardmasters_app.event_handlers.work_order_fdr.skip_material_transfer.get_user_role_profile_settings",
                    callback: function(r) {
                        if (r.message && r.message.check_box) {
                            frm.set_value('skip_transfer', 1);
                        }
                        
                        frm.doc.__settings_loaded = true;
                    }
                });
            }, 1000);
        }
    }
});