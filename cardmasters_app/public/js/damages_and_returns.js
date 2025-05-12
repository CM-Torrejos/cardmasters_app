frappe.ui.form.on('Damages and Returns', {
    refresh: function(frm) {
      // Only show the button if the document is saved
      if (!frm.is_new()) {
        frm.add_custom_button('Material Issue', () => {
          frappe.new_doc('Stock Entry', {
            custom_damages_and_returns: frm.doc.name,
            purpose: 'Material Issue'
          });
        }, 'Create'); 
      }
    }
  });
  

frappe.ui.form.on('Damages and Returns', {
    refresh: function(frm) {
      // Only show the button if the document is saved
      if (!frm.is_new()) {
        frm.add_custom_button('Work Order', () => {
          frappe.new_doc('Work Order', {
            custom_damages_and_returns: frm.doc.name,
          });
        }, 'Create'); 
      }
    }
  });
  