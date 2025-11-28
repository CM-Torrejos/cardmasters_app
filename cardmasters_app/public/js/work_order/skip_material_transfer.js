frappe.ui.form.on('Work Order', {
    refresh: function(frm) {
        // Debugging: This will prove the script is running
        console.log("Script Loaded. Status:", frm.doc.docstatus, "Is New:", frm.is_new());

        // Check if Draft (0) or New. 
        // We use docstatus === 0 to catch cases where it might be a saved draft.
        if (frm.doc.docstatus === 0 && !frm.doc.__settings_loaded) {
            
            console.log("Waiting 1 second to apply settings...");
            
            setTimeout(function() {
                frappe.call({
                    method: "cardmasters_app.cardmasters_app.event_handlers.work_order_fdr.skip_material_transfer.get_user_role_profile_settings",
                    callback: function(r) {
                        if (r.message && r.message.check_box) {
                            console.log("Applying checkbox setting!");
                            frm.set_value('skip_transfer', 1);
                        }
                        // Mark as loaded so we don't spam the API on every refresh
                        frm.doc.__settings_loaded = true;
                    }
                });
            }, 1000); // 1 second delay to beat the standard mapper
        }
    }
});