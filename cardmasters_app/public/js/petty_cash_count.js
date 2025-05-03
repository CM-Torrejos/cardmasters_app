// ------------------------------------------------------------------
// File: public/js/doctype/petty_cash_count/petty_cash_count.js
// ------------------------------------------------------------------

frappe.ui.form.on('Petty Cash Count', {
  // 1) Populate default denominations on brand-new docs
  onload: function(frm) {
    if (frm.doc.__islocal && !frm.doc.petty_cash_count_table.length) {
      const default_items = ['1000','500','200','100','50','20','10','5','1','0.25','0.05','0.01'];
      default_items.forEach(denom => {
        const row = frm.add_child('petty_cash_count_table');
        row.denomination = denom;
      });
      frm.refresh_field('petty_cash_count_table');
    }
  },

  // 2) Recalculate the overall petty cash total
  total_petty_cash_count: function(frm) {
    let total = 0;
    frm.doc.petty_cash_count_table.forEach(row => {
      total += row.amount || 0;
    });
    frm.set_value('total_petty_cash_count', total);
  },

  // 3) Add/Enable the Sync button on every render (after save/submit)
  refresh: function(frm) {
    // Add the button for any saved or submitted doc
    if (!frm.is_new()) {
      frm.add_custom_button(
        __('Sync Petty Cash Transactions'),
        () => syncPettyCashTransactions(frm)
      );
      // Disable for drafts (docstatus 0), enable for submitted (docstatus 1)
      frm.page.set_button_disabled(
        __('Sync Petty Cash Transactions'),
        frm.doc.docstatus !== 1
      );
    }
  }
});

// ------------------------------------------------------------------
// Child table handlers: Petty Cash Count Table
// ------------------------------------------------------------------

frappe.ui.form.on('Petty Cash Count Table', {
  denomination: calculate_row_amount,
  count:       calculate_row_amount,
  amount: function(frm) {
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

// ------------------------------------------------------------------
// Sync logic: Fetch & display related transactions
// ------------------------------------------------------------------

async function syncPettyCashTransactions(frm) {
  if (frm.is_new()) {
    frappe.show_alert({ message: __('Please save the document before syncing.'), indicator: 'yellow' });
    return;
  }

  try {
    await fetchUnliquidatedTransactions(frm);
    await fetchLiquidatedTransactions(frm);
    updateCashCountBalance(frm);

    frappe.show_alert({ message: __('✅ Petty Cash Transactions synced successfully!'), indicator: 'green' });
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

async function fetchUnliquidatedTransactions(frm) {
  console.log('[Unliq] Fetching…');
  frm.clear_table('unliquidated_transactions_table');

  const { message: transactions = [] } = await frappe.call({
    method: 'cardmasters_app.cardmasters_app.api.petty_cash_count.get_unliquidated_transactions',
    args: { petty_cash_count: frm.doc.name }
  });

  let total = 0;
  transactions.forEach(tx => {
    const row = frm.add_child('unliquidated_transactions_table');
    row.petty_cash_request = tx.request;
    row.petty_cash_voucher = tx.voucher_name;
    row.amount = tx.total_amount_released;
    total += tx.total_amount_released || 0;
  });

  frm.set_value('total_unliquidated', total);
  frm.refresh_field('unliquidated_transactions_table');
  console.log(`[Unliq] Added ${transactions.length} rows. Total = ${total}`);
}

async function fetchLiquidatedTransactions(frm) {
  console.log('[Liq] Fetching…');
  frm.clear_table('liquidated_transactions_table');

  const { message: transactions = [] } = await frappe.call({
    method: 'cardmasters_app.cardmasters_app.api.petty_cash_count.get_liquidated_transactions',
    args: { petty_cash_count: frm.doc.name }
  });

  let total = 0;

  // Create an array of promises for the async frappe.call inside the loop
  const promises = transactions.map(async (tx) => {
    const row = frm.add_child('liquidated_transactions_table');
    row.petty_cash_request = tx.request;
    row.petty_cash_voucher = tx.voucher_name;
    row.purchase_invoice = tx.invoice_name;

    // Fetch the grand_total of the Purchase Invoice asynchronously
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
        row.amount = invoice.grand_total;
        total += invoice.grand_total || 0;
      } else {
        console.log(`Grand Total not found for Invoice: ${tx.invoice_name}`);
      }
    } catch (error) {
      console.error(`[Sync] Error fetching grand_total for Purchase Invoice ${tx.invoice_name}:`, error);
    }
  });

  // Wait for all promises to resolve before continuing
  await Promise.all(promises);

  // Now that all the data has been fetched, update the form fields
  frm.set_value('total_liquidated', total);
  frm.refresh_field('liquidated_transactions_table');
  console.log(`[Liq] Added ${transactions.length} rows. Total = ${total}`);
  console.log('out' + total);
}


function updateCashCountBalance(frm) {
  const u = flt(frm.doc.total_unliquidated);
  const l = flt(frm.doc.total_liquidated);
  const f = flt(frm.doc.total_petty_cash_count);
  const s = flt(frm.doc.starting_petty_cash_fund);
  const balance = s - (u + l + f);
  frm.set_value('balance', balance);
  console.log(`[Balance] ${s} - ${u} + ${l} + ${f} = ${balance}`);
}


