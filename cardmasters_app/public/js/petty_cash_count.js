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
