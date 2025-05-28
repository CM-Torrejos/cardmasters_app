frappe.ui.form.on('Purchase Invoice', {
    // runs whenever the checkbox is toggled
    custom_from_revolving_fund(frm) {
      if (frm.doc.custom_from_revolving_fund) {
        frm.set_value(
          'credit_to',
          '2111 - ACCOUNT PAYABLE - RF - CM CDO'
        );
      }
    },
  
    // runs when the form is loaded or refreshed
    
  });
  