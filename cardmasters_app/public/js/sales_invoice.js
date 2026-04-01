frappe.ui.form.on('Sales Invoice', {
    refresh: function(frm) {
        if (!['Draft', 'Cancelled'].includes(frm.doc.status)) {
            frm.add_custom_button(__('Reclass to Employee AR'), function() {
                
                // 1. Ensure Journal Entry metadata is loaded in the browser
                frappe.model.with_doctype('Journal Entry', function() {
                    
                    // 2. Create a new document in the local buffer (not yet saved)
                    let journal = frappe.model.get_new_doc('Journal Entry');
                    
                    // 3. Set Header Values
                    frappe.model.set_value(journal.doctype, journal.name, {
                        company: frm.doc.company,
                        voucher_type: 'Journal Entry',
                        remark: `Reclass of ${frm.doc.name} to Employee AR`,
                        cheque_no: frm.doc.name,
                        cheque_date: frappe.datetime.nowdate()
                    });

                    // 4. Add Row 1: Credit Customer (to clear the Invoice)
                    let row1 = frappe.model.add_child(journal, 'Journal Entry Account', 'accounts');
                    frappe.model.set_value(row1.doctype, row1.name, {
                        account: frm.doc.debit_to,
                        party_type: 'Customer',
                        party: frm.doc.customer,
                        credit_in_account_currency: frm.doc.grand_total,
                        account_currency: frm.doc.currency,
                        exchange_rate: 1,
                        reference_type: 'Sales Invoice',
                        reference_name: frm.doc.name,
                        cost_center: frm.doc.cost_center || (frm.doc.items[0] && frm.doc.items[0].cost_center)
                    });

                    // 5. Add Row 2: Debit Employee (to transfer the debt)
                    let row2 = frappe.model.add_child(journal, 'Journal Entry Account', 'accounts');
                    frappe.model.set_value(row2.doctype, row2.name, {
                        account: '1455 - ADVANCES TO EMPLOYEES - CM CDO',
                        party_type: 'Employee',
                        party: '', // Left blank as requested
                        debit_in_account_currency: frm.doc.grand_total,
                        account_currency: frm.doc.currency,
                        exchange_rate: 1,
                        cost_center: frm.doc.cost_center || (frm.doc.items[0] && frm.doc.items[0].cost_center)
                    });

                    // 6. Redirect the user to the newly created form in the buffer
                    frappe.set_route('Form', 'Journal Entry', journal.name);
                });

            }, __('Create'));
        }
    }
});