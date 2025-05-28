frappe.ui.form.on('Petty Cash Count', {
    //onload: populate cash count child table with denominations and their respective counts
    onload: function(frm){
        if(frm.doc.__islocal && !frm.doc.petty_cash_count_table.length) {
            const default_items = ['1000','500','200','100','50','20','10','5','1','0.25','0.05','0.01'];
            default_items.forEach(denom => {
                const row = frm.add_child('petty_cash_count_table');
                row.denomination = denom;
            });
            frm.refresh_field('petty_cash_count_table');
        }
    },

    //"Callback" event handler for total_petty_cash_count field
    //Re-calculates overall petty cash total
    total_petty_cash_count: function(frm) {
        let total = 0;
        frm.doc.petty_cash_count_table.forEach(row => {
            total += row.amount || 0;
        })
        frm.set_value('total_petty_cash_count', total);
    },

    // on every render, generate the 'Sync Transactions button'
    refresh: function(frm){
        // When saved/submitted, add this button
        if (!frm.is_new()){
            frm.add_custom_button(
                __('Sync Petty Cash Transactions'),
                () => syncPettyCashTransactions(frm)
            );
            //disable the button if the form is in draft state
            // frm.page.set_button_disabled(
            //     __('Sync Petty Cash Transactions'),
            //     frm.doc.docstatus !== 1
            // );
        }
    }    
}
);

//petty cash count table 
frappe.ui.form.on('Petty Cash Count Table', {
    denomination: calculate_row_amount,
    count: calculate_row_amount
});

//calculates the row amount 
function calculate_row_amount(frm, cdt, cdn) {
    const row = locals[cdt][cdn];
    if (row.denomination != null & row.count != null){
        row.amount = row.denomination * row.count;
        frm.refresh_field('petty_cash_count_table');
        frm.trigger('total_petty_cash_count');
    }
}

//button click function
async function syncPettyCashTransactions(frm) {
    try {
        //Call the fetch functions, then update the balance
        await fetchLiquidatedTransactions(frm);
        await fetchUnliquidatedTransactions(frm);
        updateCashCountBalance(frm)
    }catch (err){
        console.error('[Sync] Error:', err);
        frappe.msgprint({
            title: __('Sync Error'),
            message: err.message || 'An Unknown Error has Occured',
            indicator: 'red'
        });
    }
}

//query unliquidated transactions
async function fetchUnliquidatedTransactions(frm) {
    console.log('[Unliq] Fetching…');
    frm.clear_table('unliquidated_transactions_table');

    const { message: transactions = [] } = await frappe.call({
        method: 'cardmasters_app.cardmasters_app.api.petty_cash_count_dev.get_unliquidated_transactions',
        args: { petty_cash_count: frm.doc.name },
    })

    let total = 0;
    transactions.forEach(tx => {
        const row = frm.add_child('unliquidated_transactions_table');
        row.material_request = tx.material_request;
        row.purchase_order = tx.purchase_order;
        row.amount_released = tx.amount_released;
        total += tx.amount_released;
    })

    frm.set_value('total_unliquidated', total);
    frm.refresh_field('unliquidated_transactions_table');
}

//query liquidated transactions 
async function fetchLiquidatedTransactions(frm){
    console.log('[Liq] Fetching...');
    frm.clear_table('liquidated_transactions_table');
    
    const { message: transactions = [] } = await frappe.call ({
        method: 'cardmasters_app.cardmasters_app.api.petty_cash_count_dev.get_liquidated_transactions',
        args: { petty_cash_count: frm.doc.name  },
    });

    let total = 0;

    const promises = transactions.map( async(tx) => {
        const row = frm.add_child('liquidated_transactions_table');
        row.material_request = tx.material_request;
        row.purchase_order = tx.purchase_order;
        row.purchase_invoice = tx.purchase_invoice;

        try {
            const response = await frappe.call({
                method: 'frappe.client.get',
                args: {
                    doctype: 'Purchase Invoice',
                    name: tx.invoice_name
                }
            });

            const invoice = response.message;
            if (invoice && invoice.grand_total) {
                row.amount_paid = invoice.grand_total
                total += invoice.grand_total || 0;
            }else {
                console.log(`Grand Total not found for Invoice: ${tx.invoice_name}`);
            }
        }catch(err){
            console.error(`[Sync] Error fetching grand_total for Purchase Invoice ${tx.invoice_name}:`, error);
        }

        // Let all promises finish before proceeding to set values
        await Promise.all(promises);

        // Now that all the data has been fetched, update the form fields
        frm.set_value('total_liquidated', total);
        frm.refresh_field('liquidated_transactions_table');
        console.log(`[Liq] Added ${transactions.length} rows. Total = ${total}`);
        console.log('out' + total);
    });
}

//update the cash count balance field
function updateCashCountBalance(frm) {
    const u = flt(frm.doc.total_unliquidated);
    const l = flt(frm.doc.total_liquidated);
    const f = flt(frm.doc.total_petty_cash_count);
    const s = flt(frm.doc.allocated_revolving_fund);
    const balance = s - (u + l + f);
    frm.set_value('balance', balance);
    console.log(`[Balance] ${s} - ${u} + ${l} + ${f} = ${balance}`);
}
