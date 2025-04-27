// Petty Cash Count Table
frappe.ui.form.on('Petty Cash Count', {
	onload: function(frm) {
    	// only run once on a brand-new document
    	if (frm.doc.__islocal && !frm.doc.petty_cash_count_table.length) {
        	const default_items = ['1000','500','200','100','50', '20', '10', '5', '1', '0.25', '0.05', '0.01'];
       	 
        	default_items.forEach(denom => {
            	const row = frm.add_child('petty_cash_count_table');
            	row.denomination = denom;
        	});
       	 
        	frm.refresh_field('petty_cash_count_table');
    	}
	},
	// To update the total fund whenever a child table field changes (denomination, count, or amount)
	total_petty_cash_count: function(frm) {
    	let total = 0;
    	frm.doc.petty_cash_count_table.forEach(function(row) {
        	total += row.amount || 0;  // Add the amount of each row to the total (if it exists)
    	});
    	frm.set_value('total_petty_cash_count', total);  // Set the total fund value
	}
});

frappe.ui.form.on('Petty Cash Count Table', {
  denomination: calculate_row_amount,
  count:     	calculate_row_amount,
  amount:    	function(frm) {
	frm.trigger('total_petty_cash_count');
  }
});

function calculate_row_amount(frm, cdt, cdn) {
  const row = locals[cdt][cdn];
  if (row.denomination != null && row.count != null) {
	row.amount = row.denomination * row.count;
	frm.refresh_field('petty_cash_count_table');
	frm.trigger('total_petty_cash_count');
  }
}

// Fetch Related Transactions
frappe.ui.form.on('Petty Cash Count', {
    // 1) Add the button exactly once per form load
    setup: function(frm) {
      frm.add_custom_button(
        'Sync Petty Cash Transactions',
        () => syncPettyCashTransactions(frm),
        'Actions'
      );
    },
  
    // 2) Disable the button if the doc isn't saved yet
    refresh: function(frm) {
      frm.page.set_button_disabled(
        'Sync Petty Cash Transactions',
        frm.doc.__islocal
      );
    }
  });
  
  // 3) Top-level sync orchestrator
  async function syncPettyCashTransactions(frm) {
    if (frm.doc.__islocal) {
      frappe.show_alert({
        message: 'Please save the document before syncing.',
        indicator: 'yellow'
      });
      return;
    }
  
    try {
      await fetchUnliquidatedTransactions(frm);
      await fetchLiquidatedTransactions(frm);
      updateCashCountBalance(frm);
  
      frappe.show_alert({
        message: '✅ Petty Cash Transactions synced successfully!',
        indicator: 'green'
      });
      console.log('[Sync] Completed without errors.');
    } catch (err) {
      console.error('[Sync] Error:', err);
      frappe.msgprint({
        title: __('Sync Error'),
        message: err.message || __('An unknown error occurred.'),
        indicator: 'red'
      });
    }
  }
  
  // 4) Fetch and populate unliquidated transactions
  async function fetchUnliquidatedTransactions(frm) {
    console.log('[Unliq] Fetching…');
    frm.clear_table('unliquidated_transactions');
  
    const { message: transactions = [] } = await frappe.call({
      method: 'your_app.petty_cash_count.api.get_unliquidated_transactions',
      args: { petty_cash_count: frm.doc.name }
    });
  
    let total = 0;
    transactions.forEach(tx => {
      const row = frm.add_child('unliquidated_transactions');
      row.petty_cash_request = tx.request;
      row.petty_cash_voucher = tx.voucher_name;
      row.amount = tx.total_amount_released;
      total += tx.total_amount_released || 0;
    });
  
    frm.set_value('total_unliquidated', total);
    frm.refresh_field('unliquidated_transactions');
    console.log(`[Unliq] Added ${transactions.length} rows. Total = ${total}`);
  }
  
  // 5) Fetch and populate liquidated transactions
  async function fetchLiquidatedTransactions(frm) {
    console.log('[Liq] Fetching…');
    frm.clear_table('liquidated_transactions');
  
    const { message: transactions = [] } = await frappe.call({
      method: 'your_app.petty_cash_count.api.get_liquidated_transactions',
      args: { petty_cash_count: frm.doc.name }
    });
  
    let total = 0;
    transactions.forEach(tx => {
      const row = frm.add_child('liquidated_transactions');
      row.petty_cash_request = tx.request;
      row.petty_cash_voucher = tx.voucher_name;
      row.petty_cash_invoice = tx.invoice_name;
      row.amount = tx.total_amount_released;
      total += tx.total_amount_released || 0;
    });
  
    frm.set_value('total_liquidated', total);
    frm.refresh_field('liquidated_transactions');
    console.log(`[Liq] Added ${transactions.length} rows. Total = ${total}`);
  }
  
  // 6) Recalculate the overall balance client-side
  function updateCashCountBalance(frm) {
    const u = flt(frm.doc.total_unliquidated);
    const l = flt(frm.doc.total_liquidated);
    const f = flt(frm.doc.total_fund);
    const balance = u + l + f;
  
    frm.set_value('cash_count_balance', balance);
    console.log(`[Balance] ${u} + ${l} + ${f} = ${balance}`);
  }
  

