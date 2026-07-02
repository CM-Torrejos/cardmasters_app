frappe.ui.form.on('Stock Entry', {
  onload(frm) {
    // only for Manufacture pick-type entries from a Work Order
    if (
      !frm.doc.__islocal ||
      frm.doc.docstatus !== 0 ||
      frm.doc.purpose !== 'Material Transfer for Manufacture' ||
      !frm.doc.work_order
    ) return;
    
    // pull the WO, then map its custom_item_specifics
    frappe.db.get_doc('Work Order', frm.doc.work_order)
    .then(wo => {
      wo.required_items.forEach(req => {
        frm.doc.items.forEach(row => {
          if (row.item_code === req.item_code && !row.custom_item_specifics) {
            row.custom_item_specifics = req.custom_item_specifics;
          }
        });
      });
      frm.refresh_field('items');
    });
  },
  
  refresh: function(frm) {
        // We check if the doc is new so we don't overwrite existing saved data unintentionally
        if (frm.is_new()) {
            toggle_batched_field(frm);
        }

        add_repack_actions(frm);
  },

  stock_entry_type: function(frm) {
        toggle_batched_field(frm);
    }
  
});

function add_repack_actions(frm) {
    if (frm.doc.docstatus !== 1 || frm.doc.purpose !== 'Repack') {
        return;
    }

    frm.add_custom_button(__('Deliver'), function() {
        make_delivery_note_from_repack(frm);
    }, __('Actions'));
    frm.add_custom_button(__('Repack'), function() {
        make_repack_stock_entry_from_repack(frm);
    }, __('Actions'));
}

async function make_delivery_note_from_repack(frm) {
    const finished_good_row = get_repack_finished_good_output_row(frm);

    if (!finished_good_row) {
        frappe.msgprint(__('Could not find a finished good output row with a target warehouse and batch.'));
        return;
    }

    await with_doctype('Delivery Note');

    const delivery_note = frappe.model.get_new_doc('Delivery Note');
    delivery_note.company = frm.doc.company;
    delivery_note.custom_batched = frm.doc.custom_batched || 1;
    delivery_note.custom_repack_reference = frm.doc.name;

    const delivery_note_item = frappe.model.add_child(
        delivery_note,
        'Delivery Note Item',
        'items'
    );

    delivery_note_item.item_code = finished_good_row.item_code;
    delivery_note_item.item_name = finished_good_row.item_name;
    delivery_note_item.description = finished_good_row.description;
    delivery_note_item.qty = finished_good_row.qty;
    delivery_note_item.stock_qty = finished_good_row.transfer_qty || finished_good_row.qty;
    delivery_note_item.uom = finished_good_row.uom;
    delivery_note_item.stock_uom = finished_good_row.stock_uom;
    delivery_note_item.conversion_factor = finished_good_row.conversion_factor || 1;
    delivery_note_item.warehouse = finished_good_row.t_warehouse;
    delivery_note_item.batch_no = finished_good_row.batch_no;
    delivery_note_item.use_serial_batch_fields = 1;
    delivery_note_item.custom_item_specifics = finished_good_row.custom_item_specifics;

    frappe.set_route('Form', 'Delivery Note', delivery_note.name);
}

function get_repack_finished_good_output_row(frm) {
    const rows = (frm.doc.items || []).filter(row => row.t_warehouse && row.batch_no);

    if (rows.length === 1) {
        return rows[0];
    }

    const finished_item_rows = rows.filter(row => cint(row.is_finished_item));
    if (finished_item_rows.length === 1) {
        return finished_item_rows[0];
    }

    return null;
}

async function make_repack_stock_entry_from_repack(frm) {
    const finished_good_row = get_repack_finished_good_output_row(frm);

    if (!finished_good_row) {
        frappe.msgprint(__('Could not find a finished good output row with a target warehouse and batch.'));
        return;
    }

    await with_doctype('Stock Entry');

    const stock_entry = frappe.model.get_new_doc('Stock Entry');
    stock_entry.purpose = 'Repack';
    stock_entry.stock_entry_type = 'Repack';
    stock_entry.company = frm.doc.company;
    stock_entry.custom_work_order_for_repack = frm.doc.custom_work_order_for_repack;
    stock_entry.custom_sales_order = frm.doc.custom_sales_order;
    stock_entry.custom_batched = 0;

    const row = frappe.model.add_child(stock_entry, 'Stock Entry Detail', 'items');
    row.item_code = finished_good_row.item_code;
    row.item_name = finished_good_row.item_name;
    row.description = finished_good_row.description;
    row.qty = finished_good_row.qty;
    row.transfer_qty = finished_good_row.transfer_qty || finished_good_row.qty;
    row.uom = finished_good_row.uom;
    row.stock_uom = finished_good_row.stock_uom;
    row.conversion_factor = finished_good_row.conversion_factor || 1;
    row.s_warehouse = finished_good_row.t_warehouse;
    row.batch_no = finished_good_row.batch_no;
    row.use_serial_batch_fields = 1;
    row.custom_item_specifics = finished_good_row.custom_item_specifics;

    frappe.set_route('Form', 'Stock Entry', stock_entry.name);
}

function with_doctype(doctype) {
    return new Promise(resolve => {
        frappe.model.with_doctype(doctype, resolve);
    });
}

function toggle_batched_field(frm) {
    if (frm.doc.stock_entry_type === 'Manufacture' && frm.doc.work_order) {
        frappe.db.get_value('Work Order', frm.doc.work_order, 'sales_order')
            .then(r => {
                let so = r.message ? r.message.sales_order : null;
                if (so) {
                    frm.set_value('custom_batched', 1);
                } else {
                    frm.set_value('custom_batched', 0);
                }
            });
    } else if (frm.doc.stock_entry_type === 'Repack') {
        return;
    } else {
        frm.set_value('custom_batched', 0);
    }
}
