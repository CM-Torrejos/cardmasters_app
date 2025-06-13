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
  
  // refresh(frm) {
  //   // only show button on Manufacture Stock Entry
  //   if (frm.doc.stock_entry_type === 'Manufacture' && frm.doc.work_order) {
  //     frm.add_custom_button('Fetch Additional Items', () => {
  //       // load the Work Order
  //       frappe.db.get_doc('Work Order', frm.doc.work_order)
  //       .then(wo => {
  //         // loop through each row in custom_additional_items
  //         wo.custom_additional_items.forEach(additional => {
  //           // create a new row in the Stock Entry items table
  //           let new_row = frappe.model.add_child(frm.doc, 'Stock Entry Detail', 'items');
  //           frappe.model.set_value(new_row.doctype, new_row.name, 's_warehouse', additional.s_warehouse);
  //           frappe.model.set_value(new_row.doctype, new_row.name, 'item_code', additional.item_code);
            
  //           frappe.model.set_value(new_row.doctype, new_row.name, 'qty', additional.qty);
  //           frappe.model.set_value(new_row.doctype, new_row.name, 'custom_item_specifics', additional.custom_item_specifics);
            
            
  //         });
  //         // re-render the items table
  //         frm.refresh_field('items');
  //       });
  //     });
  //   }
  // }
});



