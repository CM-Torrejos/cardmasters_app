frappe.ui.form.on('Material Request', {    
    refresh: function(frm) {
        if (frm.doc.docstatus === 1 && frm.doc.material_request_type === 'Customer Provided') {
            // Remove the default "Material Receipt" button (if present)
            setTimeout(() => {
                frm.page.remove_inner_button(__('Material Receipt'), __('Create'));
            }, 100);

            // Add our custom "Receive Customer Provided Item" button
            frm.add_custom_button(__('Receive Customer Provided Item'), async () => {
                try {
                    // Call the backend Python function
                    const response = await frappe.call({
                        method: 'cardmasters_app.cardmasters_app.api.material_request.make_rcpi_stock_entry',
                        args: {
                            material_request_name: frm.doc.name
                        }
                    });

                    // If the Python call returned a Stock Entry name, redirect to it
                    if (response.message) {
                        frappe.set_route('Form', 'Stock Entry', response.message);
                    }
                } catch (err) {
                    // In case something goes wrong, show a frappe error
                    frappe.show_alert({
                        message: __('Could not create the Stock Entry: {0}', [err.message]),
                        indicator: 'red'
                    });
                }
            }, __('Create'));
        }

        // (Handle the Material Transfer button case here, if you have one)
        else if (frm.doc.docstatus === 1 && frm.doc.material_request_type === 'Material Transfer' && frm.doc.work_order) {
            // … your existing add_material_transfer_button(frm) call
            
        }
    },
    
    validate: function(frm) {
        // Only enforce when Purpose is exactly "Customer Provided"
        if (frm.doc.material_request_type === 'Customer Provided') {
            // If there are no items, nothing to check
            console.log('validate function running')
            if (!frm.doc.items || frm.doc.items.length === 0) {
                return;
            }
            
            // Collect all sales_order values from each row
            let sales_orders = frm.doc.items.map(function(row) {
                return row.sales_order || null;
            });
            
            // If any row has no sales_order set, throw immediately
            for (let i = 0; i < sales_orders.length; i++) {
                if (!sales_orders[i]) {
                    frappe.throw(__(
                        'Row #{0} must have a Sales Order when Purpose is "Customer Provided".',
                        [frm.doc.items[i].idx]
                    ));
                }
            }
            
            // Now check that they’re all identical
            let first_so = sales_orders[0];
            let mismatch = sales_orders.some(function(so) {
                return so !== first_so;
            });
            
            if (mismatch) {
                frappe.throw(__('All items must reference the same Sales Order when Purpose is "Customer Provided".'));
            }
            
            console.log('poggers')
        }
    },
}); 

function add_material_transfer_button(frm) {
    frm.add_custom_button(__('Material Transfer (For Manufacture)'), () => {
        // const items = frm.doc.items.map(r => ({
        //     item_code: r.item_code,
        //     qty:       r.qty,
        //     ...(r.custom_item_specifics ? JSON.parse(r.custom_item_specifics) : {})
        // }));

        let mapped_items = (frm.doc.items || []).map(row => {
            return {
                item_code: row.item_code,
                qty: row.qty,
                uom: row.uom,
                stock_uom: row.stock_uom,
                transfer_qty: row.qty,
                t_warehouse: row.warehouse,
                material_request: frm.doc.name,
                material_request_item: row.name,
                basic_rate: '0',
                custom_item_specifics: row.custom_item_specifics,
                use_serial_batch_fields: '1'
            };
        });
        
        frappe.new_doc('Stock Entry', {
            stock_entry_type:    'Material Transfer for Manufacture',
            work_order:          frm.doc.work_order,
            material_request:    frm.doc.name,
            items: mapped_items
        });
    }, __('Create'));
}

// WIP
function add_customer_received_mr_button(frm) {
    if (!frm.doc.work_order) return;
    
    frm.add_custom_button(__('Fetch Batched'), () => {
        // 1. Load the WO and grab its raw‐material lines
        frappe.db.get_doc('Work Order', frm.doc.work_order)
        .then(wo => {
            const materials = wo.required_items || wo.items || [];
            if (!materials.length) {
                frappe.msgprint(__('No material lines on this Work Order'));
                return;
            }
            
            // 2. Collect all item_codes and fetch only those with your custom flag
            const codes = materials.map(m => m.item_code);
            return frappe.db.get_list('Item', {
                fields: ['name'],
                filters: {
                    custom_requires_custom_batch: 1,
                    name: ['in', codes]
                }
            })
            .then(items => {
                const eligible = new Set(items.map(i => i.name));
                // 3. Filter the WO lines down to only flagged items
                const filtered = materials.filter(m => eligible.has(m.item_code));
                
                if (!filtered.length) {
                    frappe.msgprint(__('No items require custom batch'));
                    return;
                }
                
                // 4. Clear existing table, add only the filtered rows
                frm.clear_table('items');
                filtered.forEach(mat => {
                    frm.add_child('items', {
                        item_code: mat.item_code,
                        qty: mat.required_qty || mat.qty,
                        uom: mat.uom,
                        custom_item_specifics: mat.custom_item_specifics
                    });
                });
                frm.refresh_field('items');
                
                frappe.show_alert({
                    message: __('Fetched {0} custom‐batched items', [filtered.length]),
                    indicator: 'green'
                });
            });
        })
        .catch(err => {
            frappe.msgprint(__('Could not load Work Order: {0}', [err.message]));
        });
    });
}

function add_rcpi_button(frm) {
    frm.add_custom_button(__('Receive Customer Provided Item'), () => {
        let sales_order = frm.doc.items[0].sales_order;
        let mapped_items = (frm.doc.items || []).map(row => {
            return {
                item_code: row.item_code,
                qty: row.qty,
                uom: row.uom,
                stock_uom: row.stock_uom,
                transfer_qty: row.qty,
                t_warehouse: row.warehouse,
                basic_rate: '0',
                custom_item_specifics: row.custom_item_specifics,
                use_serial_batch_fields: '1'
            };
        });
        
        frappe.new_doc('Stock Entry', {
            stock_entry_type: 'Material Receipt',
            custom_sales_order: sales_order,
            items: mapped_items,
        });
        
    }, __('Create'));
}
