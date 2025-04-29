frappe.ui.form.on('Damages and Returns', {
    refresh: function(frm) {
      // Only show the button if the document is saved
      if (!frm.is_new()) {
        frm.add_custom_button('Material Issue', () => {
          frappe.new_doc('Stock Entry', {
            custom_damages_and_returns: frm.doc.name,
            purpose: 'Material Issue'
          });
        }); // Group it under 'Create' if you like
      }
    }
  });
  