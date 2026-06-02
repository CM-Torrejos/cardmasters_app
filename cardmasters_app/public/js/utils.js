frappe.provide('cardmasters.utils');

cardmasters.utils.sales_order_print_preview = function(frm) {
    const target_field = frm.fields_dict.custom_sales_order_print || frm.fields_dict.sales_order_print;

    if (!target_field) {
        console.warn("Print Preview: Neither 'custom_sales_order_print' nor 'sales_order_print' fields were found.");
        return;
    }

    if (frm.doc.sales_order) {
        frappe.call({
            method: 'cardmasters_app.cardmasters_app.api.sales_order.get_sales_order_html',
            args: {
                sales_order_name: frm.doc.sales_order
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
}