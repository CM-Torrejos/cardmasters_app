// Copyright (c) 2025, Shan Torrejos and contributors
// For license information, please see license.txt

frappe.ui.form.on('Artist Card', {
    refresh: function(frm) {
        
        if (cardmasters.utils && cardmasters.utils.sales_order_print_preview) {
            cardmasters.utils.sales_order_print_preview(frm);
        } else {
            console.error('Cardmasters Utils not loaded. Check hooks.py');
        }
        
        // Only show action buttons in Layouting state on saved docs
        if (frm.doc.workflow_state === "Layouting" && !frm.is_new()) {
            
            // 1) Start button
            if (!frm.doc.timesheet || !frm.doc.timesheet.length) {
                frm.add_custom_button('Start', () => {
                    const now = frappe.datetime.now_datetime();
                    const row = frm.add_child('timesheet');
                    row.from_time = now;
                    
                    frm.refresh_field('timesheet');
                    frm.save(); // Single save
                }).addClass('btn-primary');
            }
            
            const last = frm.doc.timesheet ? frm.doc.timesheet.slice(-1)[0] : null;
            
            // 2) Pause button
            if (last && last.from_time && !last.to_time) {
                frm.add_custom_button('Pause', () => {
                    const now = frappe.datetime.now_datetime();
                    frappe.model.set_value(last.doctype, last.name, 'to_time', now);
                    
                    const mins = moment.duration(moment(now).diff(moment(last.from_time))).asMinutes();
                    frappe.model.set_value(last.doctype, last.name, 'time_in_minutes', mins);
                    
                    calculate_and_set_total(frm);
                    frm.save(); // Single save
                }).addClass('btn-danger');
                
            // 3) Resume button
            } else if (last && last.to_time) {
                frm.add_custom_button('Resume', () => {
                    const now = frappe.datetime.now_datetime();
                    const row = frm.add_child('timesheet');
                    row.from_time = now;
                    
                    frm.refresh_field('timesheet');
                    frm.save(); // Single save
                }).addClass('btn-success');
            }
        }
    }
});

// Sets finished_total_time on the client side before save
function calculate_and_set_total(frm) {
    const total = (frm.doc.timesheet || [])
        .reduce((sum, r) => sum + (r.time_in_minutes || 0), 0);
    
    frm.set_value('finished_total_time', total);
}