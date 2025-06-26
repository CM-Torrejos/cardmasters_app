frappe.ui.form.on('Payment Entry', {
    // fire on load/refresh and whenever the key fields change
    refresh: set_misc_defaults,
    payment_type: set_misc_defaults,
    party_type: set_misc_defaults,
    party: set_misc_defaults
  });
  
  function set_misc_defaults(frm) {
    // only for Pay + Cheque, Supplier = MISCELLANEOUS SUPPLIER
    if (
      frm.doc.payment_type === 'Pay' &&
      frm.doc.party_type === 'Supplier' &&
      frm.doc.party === 'DISBURSEMENT OFFICER'
    ) {
      // use frm.doc.party_balance (ERPNext already fetched it for you)
      // frm.set_value('paid_amount', (frm.doc.party_balance * -1));
      frm.set_value('paid_to', '2111 - ACCOUNT PAYABLE - RF - CM CDO');
    }
  }