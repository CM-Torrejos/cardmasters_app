frappe.ui.form.on('Stock Entry', {
  onload(frm) {
    // only for Manufacture pick-type entries from a Work Order
    if (
      !frm.doc.__islocal ||
      frm.doc.docstatus !== 0 ||
      frm.doc.purpose !== 'Material Transfer for Manufacture' ||
      !frm.doc.work_order
    ) return;
    
    // pull the WO, then map its custom_item_specifics
    frappe.db.get_doc('Work Order', frm.doc.work_order)
    .then(wo => {
      wo.required_items.forEach(req => {
        frm.doc.items.forEach(row => {
          if (row.item_code === req.item_code && !row.custom_item_specifics) {
            row.custom_item_specifics = req.custom_item_specifics;
          }
        });
      });
      frm.refresh_field('items');
    });
  },
  
  refresh: function(frm) {
        // We check if the doc is new so we don't overwrite existing saved data unintentionally
        if (frm.is_new()) {
            toggle_batched_field(frm);
        }
  },

  stock_entry_type: function(frm) {
        toggle_batched_field(frm);
    }
  
});


function toggle_batched_field(frm) {
    if (frm.doc.stock_entry_type === 'Manufacture') {
        frm.set_value('custom_batched', 1);
    } else {
        // Optional: Uncheck if it's not Manufacture. 
        // Remove the 'else' block if you want to allow it to remain checked manually.
        frm.set_value('custom_batched', 0);
    }
}



