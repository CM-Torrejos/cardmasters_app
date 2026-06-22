frappe.ui.form.on('Credit Memo', {
    refresh: function(frm) {
        // Submitted memos are immutable. In particular, legacy memos have no
        // stored sponsored/commercial totals, so recalculating them on refresh
        // would make the form dirty and cause an update-after-submit error.
        if (frm.doc.docstatus !== 0) {
            return;
        }

        set_sales_order_grand_total(frm);
        set_credit_memo_totals(frm);
    },

    sales_order: function(frm) {
        set_sales_order_grand_total(frm);
    },

    validate: function(frm) {
        validate_sponsored_quantities(frm);
        set_credit_memo_totals(frm);

        if (frm.doc.sales_order) {
            
            // 1. Return an explicit Promise so Frappe halts the save sequence
            return new Promise((resolve, reject) => {
                
                frappe.db.get_value('Sales Order', frm.doc.sales_order, 'custom_sponsored')
                    .then(r => {
                        // Check if the value exists and is 0/false
                        if (r.message && !r.message.custom_sponsored) {
                            
                            // 2. Explicitly flag the form as invalid
                            frappe.validated = false;
                            
                            // 3. Use a 50ms timeout to bypass the DOM freeze collision
                            setTimeout(() => {
                                frappe.msgprint({
                                    title: __('Notice'),
                                    indicator: 'orange',
                                    message: __('The linked Sales Order is not marked as Sponsored')
                                });
                            }, 50);
                            
                            // 4. Reject the promise to completely abort the save
                            reject(); 
                            
                        } else {
                            // If it IS sponsored, resolve the promise and let it save
                            resolve(); 
                        }
                    });
            });
        }
    }
});

frappe.ui.form.on('Credit Memo Sponsored Item', {
    sponsored_quantity: function(frm, cdt, cdn) {
        set_sponsored_item_amount(frm, cdt, cdn);
    },

    sponsored_rate: function(frm, cdt, cdn) {
        set_sponsored_item_amount(frm, cdt, cdn);
    },

    sponsored_items_table_remove: function(frm) {
        set_credit_memo_totals(frm);
    }
});

function set_sponsored_item_amount(frm, cdt, cdn) {
    let row = locals[cdt][cdn];

    if (flt(row.sponsored_quantity) > flt(row.quantity)) {
        frappe.model.set_value(cdt, cdn, 'sponsored_quantity', row.quantity);
        frappe.throw(__('Sponsored Quantity cannot be greater than Quantity for item {0}.', [row.item_code || row.idx]));
        return;
    }

    let sponsored_amount = flt(row.sponsored_quantity) * flt(row.sponsored_rate);

    frappe.model.set_value(cdt, cdn, 'sponsored_amount', sponsored_amount)
        .then(() => set_credit_memo_totals(frm));
}

function set_credit_memo_totals(frm) {
    // Also guard asynchronous callbacks that may finish after submission.
    if (frm.doc.docstatus !== 0) {
        return;
    }

    let sponsored_total = (frm.doc.sponsored_items_table || []).reduce(function(sum, row) {
        return sum + flt(row.sponsored_amount);
    }, 0);
    let sales_order_grand_total = flt(frm._sales_order_grand_total);

    frm.set_value('sponsored_amount', sponsored_total);
    frm.set_value('commercial_amount', sales_order_grand_total - sponsored_total);
}

function set_sales_order_grand_total(frm) {
    if (!frm.doc.sales_order) {
        frm._sales_order_grand_total = 0;
        set_credit_memo_totals(frm);
        return;
    }

    frappe.db.get_value('Sales Order', frm.doc.sales_order, 'grand_total')
        .then(function(r) {
            frm._sales_order_grand_total = flt(r.message && r.message.grand_total);
            set_credit_memo_totals(frm);
        });
}

function validate_sponsored_quantities(frm) {
    (frm.doc.sponsored_items_table || []).forEach(function(row) {
        if (flt(row.sponsored_quantity) > flt(row.quantity)) {
            frappe.throw(__('Sponsored Quantity cannot be greater than Quantity for item {0}.', [row.item_code || row.idx]));
        }
    });
}
