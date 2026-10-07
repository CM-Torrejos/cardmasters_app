frappe.ui.form.on('Sales Order', {
    refresh(frm) {
        if (frm.doc.docstatus !== 1 || !frappe.user.has_role('System Manager')) return;
        frm.add_custom_button(__('Submit Delivery Backlog'), async () => {
            if (frm.is_dirty()) {
                frappe.msgprint(__('Save the Sales Order before submitting delivery backlog.'));
                return;
            }
            const response = await frappe.call({
                method: 'cardmasters_app.cardmasters_app.api.delivery_backlog.get_delivery_backlog',
                args: {sales_order: frm.doc.name}, freeze: true
            });
            const notes = response.message || [];
            if (!notes.length) {
                frappe.msgprint(__('There are no draft Delivery Notes linked to this Sales Order.'));
                return;
            }
            const dialog = new frappe.ui.Dialog({
                title: __('Submit Delivery Backlog'),
                fields: [
                    {fieldtype: 'MultiCheck', fieldname: 'delivery_notes', label: __('Delivery Notes'),
                        options: notes.map(note => ({label: `${note.name} (${note.posting_date})`, value: note.name})),
                        columns: 1,
                        on_change() {
                            const selected = dialog.get_value('delivery_notes') || [];
                            if (selected.length === 1) {
                                const note = notes.find(note => note.name === selected[0]);
                                dialog.set_value('target_month', note.posting_date.slice(0, 7) + '-01');
                            }
                        }},
                    {fieldtype: 'Date', fieldname: 'target_month', label: __('Target Month'), reqd: 1,
                        default: notes[0].posting_date.slice(0, 7) + '-01',
                        description: __('All new stock entries and selected Delivery Notes will post on the first day of this month at 00:00:00.')},
                    {fieldtype: 'HTML', options: `<p>${__('This submits the selected Delivery Notes and creates or amends the required Work Orders and stock entries. Production Branch will be Cagayan de Oro.')}</p>`}
                ],
                primary_action_label: __('Submit Selected Backlog'),
                async primary_action(values) {
                    if (!values.delivery_notes || !values.delivery_notes.length) {
                        frappe.msgprint(__('Select at least one Delivery Note.'));
                        return;
                    }
                    dialog.get_primary_btn().prop('disabled', true);
                    try {
                        const response = await frappe.call({
                            method: 'cardmasters_app.cardmasters_app.api.delivery_backlog.submit_delivery_backlog',
                            args: {sales_order: frm.doc.name, delivery_notes: JSON.stringify(values.delivery_notes), target_month: values.target_month},
                            freeze: true, freeze_message: __('Submitting delivery backlog...')
                        });
                        dialog.hide();
                        const result = response.message;
                        const links = result.delivery_notes.map(name => frappe.utils.get_form_link('Delivery Note', name, true));
                        frappe.msgprint({title: __('Backlog Submitted'), indicator: 'green',
                            message: __('Submitted: {0}<br>Work Orders created/submitted: {1}<br>Stock Entries created: {2}',
                                [links.join(', '), result.work_orders.length, result.stock_entries.length])});
                        await frm.reload_doc();
                    } finally {
                        dialog.get_primary_btn().prop('disabled', false);
                    }
                }
            });
            dialog.show();
        }, __('Actions'));
    }
});
