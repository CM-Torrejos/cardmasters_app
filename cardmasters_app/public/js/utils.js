frappe.provide('cardmasters.utils');
frappe.provide("erpnext.utils");

cardmasters.utils.sales_order_print_preview = function(frm) {
    const target_field = frm.fields_dict.custom_sales_order_print || frm.fields_dict.sales_order_print;

    if (!target_field) {
        console.warn("Print Preview: Neither 'custom_sales_order_print' nor 'sales_order_print' fields were found.");
        return;
    }

    const sales_order_name = frm.doc.sales_order || frm.doc.custom_document_id;

    if (!sales_order_name) {
        return;
    }

    if (!frm.doc.sales_order && frm.doc.custom_document_id) {
        frappe.db.get_value('Sales Order', frm.doc.custom_document_id, 'name')
        .then(r => {
            if (r.message && r.message.name) {
                render_sales_order_print_preview(target_field, frm.doc.custom_document_id);
            }
        });
        return;
    }

    render_sales_order_print_preview(target_field, sales_order_name);
}

function render_sales_order_print_preview(target_field, sales_order_name) {
    frappe.call({
        method: 'cardmasters_app.cardmasters_app.api.sales_order.get_sales_order_html',
        args: {
            sales_order_name: sales_order_name
        },
        callback: function(r) {
            if (r.message) {
                const iframe = document.createElement("iframe");
                iframe.src = "about:blank";
                iframe.style.width = "800px";
                iframe.style.minHeight = "1000px";
                iframe.style.border = "1px solid #ccc";
                iframe.setAttribute("scrolling", "no");

                // Append the iframe to the wrapper FIRST (Browsers render better this way)
                target_field.$wrapper
                    .empty()
                    .append(iframe);

                // Write the content
                const doc = iframe.contentWindow.document;
                doc.open();
                doc.write(r.message);
                doc.close();

                // Inject CSS to handle the layout inside
                const style = doc.createElement("style");
                style.innerHTML = `
                    body {
                        margin: 0;
                        padding: 0;
                        overflow: hidden !important;
                    }
                    .print-format-toolbar { display: none !important; }
                `;
                doc.head.appendChild(style);

                // SMART RESIZE: Use ResizeObserver instead of setTimeout
                // This watches the content. If an image loads 1 second later, this detects it and resizes.
                if (window.ResizeObserver) {
                    // Disconnect any previous observer attached to this iframe to prevent memory leaks
                    if (iframe._resizeObserver) {
                        iframe._resizeObserver.disconnect();
                    }
                    const resizeObserver = new ResizeObserver(entries => {
                        // Calculate height (body + buffer)
                        const newHeight = doc.body.scrollHeight + 50;
                        iframe.style.height = newHeight + "px";
                    });
                    resizeObserver.observe(doc.body);
                    // Store reference for cleanup on next call
                    iframe._resizeObserver = resizeObserver;
                } else {
                    // Fallback for very old browsers (unlikely needed, but safe)
                    iframe.onload = function() {
                        setTimeout(() => {
                            iframe.style.height = (doc.body.scrollHeight + 50) + "px";
                        }, 500);
                    };
                }
            }
        }
    });
}

/**
 * OVERRIDE: erpnext.utils.copy_value_in_all_rows
 * 
 * Reason for Modification:
 * The native ERPNext utility has specific limitations that prevent it from working
 * effectively with customized header-to-child field syncing. This override patches 
 * those limitations while remaining backward-compatible with standard Frappe calls.
 * 
 * Key Changes Introduced:
 * 1. Force-Updates Child Rows: The native code only sets the child value if the child 
 *    field is completely empty (`if (!cl[i][fieldname])`). This override removes that 
 *    check, forcing all child rows to update every time the parent field changes.
 * 
 * 2. Mismatched Fieldname Mapping: The native code requires the parent field and child 
 *    field to have the exact same name. We added an optional `target_fieldname` parameter 
 *    so custom parent fields (e.g., `custom_branch`) can populate standard child fields 
 *    (e.g., `branch`). If omitted, it gracefully falls back to the parent `fieldname`.
 * 
 * 3. Supports Value Clearing: By setting `var val = d[fieldname] || ""`, if a user clears 
 *    the parent field, that blank/empty state will now properly cascade to the children.
 * 
 * 4. Safer Doc Fetching: Added a fallback to `doc` in case `locals[dt][dn]` is not yet 
 *    fully initialized in the DOM.
 * 
 * @param {Object} doc - The current document object
 * @param {String} dt - Parent Doctype
 * @param {String} dn - Parent Docname
 * @param {String} table_fieldname - Fieldname of the child table
 * @param {String} fieldname - Fieldname on the parent to read from
 * @param {String} [target_fieldname] - (Custom) Fieldname on the child to write to. Defaults to `fieldname`.
 */
erpnext.utils.copy_value_in_all_rows = function (doc, dt, dn, table_fieldname, fieldname, target_fieldname) {
    var d = (locals[dt] && locals[dt][dn]) || doc;
    if (d) {
        var val = d[fieldname] || "";
        var cl = doc[table_fieldname] || [];
        var target = target_fieldname || fieldname;

        for (var i = 0; i < cl.length; i++) {
            cl[i][target] = val;
        }
    }
    refresh_field(table_fieldname);
};