// Purchase Order → force zero rates on every line
frappe.ui.form.on('Purchase Order Item', {
    // When you manually add a new row…
    items_add(frm, cdt, cdn) {
      frappe.model.set_value(cdt, cdn, 'basic_rate', 0);
      frappe.model.set_value(cdt, cdn, 'rate', 0);
    },
    // When you choose or change the Item in a row…
    item_code(frm, cdt, cdn) {
      frappe.model.set_value(cdt, cdn, 'basic_rate', 0);
      frappe.model.set_value(cdt, cdn, 'rate', 0);
    }
  });
  
  // Purchase Order → on load or any refresh (e.g. after mapping from MR)
  frappe.ui.form.on('Purchase Order', {
    refresh(frm) {
      // Only do this for new documents (so you don’t overwrite rates on an existing PO)
      if (frm.is_new()) {
        frm.doc.items.forEach(function(row) {
          frappe.model.set_value(row.doctype, row.name, 'basic_rate', 0);
          frappe.model.set_value(row.doctype, row.name, 'rate', 0);
        });
      }
    }
  });
  