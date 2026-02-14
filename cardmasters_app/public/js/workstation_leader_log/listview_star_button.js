frappe.provide("frappe.cardmasters");
frappe.cardmasters.starred_cache = [];

// Inject CSS
frappe.dom.set_style(`
    .star-toggle-btn[data-starred="true"] i {
        color: #ffc107 !important; /* Yellow */
    }
    .star-toggle-btn[data-starred="true"] i::before {
        content: "\\f005" !important; /* Solid Star */
    }
`);

// Override the Render function to trigger the Fetch
const original_render = frappe.views.ListView.prototype.render;
frappe.views.ListView.prototype.render = function() {
    original_render.call(this);

    // Only run for Work Orders
    try {
        if (this.doctype === 'Work Order') {
            const names = this.data.map(d => d.name);
            if (names.length > 0) {
                frappe.call({
                    method: "cardmasters_app.cardmasters_app.doctype.workstation_leader_log.workstation_leader_log.get_starred_work_orders",
                    args: { names: names },
                    callback: (r) => {
                        if (r.message) {
                            // 1. If not a leader, hide all stars immediately
                            if (r.message.is_leader === false) {
                                $(".star-toggle-btn").hide();
                                return;
                            }

                            // 2. Access the 'starred' key from the object
                            const starred_items = r.message.starred || [];
                            frappe.cardmasters.starred_cache = starred_items.map(n => n.toUpperCase());

                            // 3. Update UI attributes
                            $(".star-toggle-btn").each(function() {
                                const name = $(this).attr('data-name').toUpperCase();
                                if (frappe.cardmasters.starred_cache.includes(name)) {
                                    $(this).attr('data-starred', 'true');
                                } else {
                                    $(this).attr('data-starred', 'false');
                                }
                            });
                        }
                    }
                });
            }
        }
    } catch (e) {
        console.error("Star Toggle Render Error:", e);
    }
};

const original_meta_html = frappe.views.ListView.prototype.get_meta_html;
frappe.views.ListView.prototype.get_meta_html = function(doc) {
    let html = original_meta_html.call(this, doc);
    
    try {
        if (this.doctype !== 'Work Order') return html;

        const is_starred = (frappe.cardmasters.starred_cache || []).includes(doc.name.toUpperCase());

        return `
            <span class="list-row-like star-toggle-btn" 
                data-name="${doc.name}"
                data-starred="${is_starred ? 'true' : 'false'}"
                onclick="frappe.cardmasters.toggle_star('${doc.name}', this); event.stopPropagation();"
                style="margin-right: 15px; cursor: pointer; display: inline-block;">
                <i class="fa fa-star-o text-muted" style="pointer-events: none;"></i>
            </span>
        ` + html;
    } catch (e) {
        console.error("Star Toggle Meta HTML Error:", e);
        return html;
    }
};

frappe.cardmasters.toggle_star = function(docname, element) {
    try {
        const $wrapper = $(element);
        const is_on = $wrapper.attr('data-starred') === 'true';
        const next_state = is_on ? 'false' : 'true';

        // Optimistic UI Change
        $wrapper.attr('data-starred', next_state);

        frappe.call({
            method: "cardmasters_app.cardmasters_app.doctype.workstation_leader_log.workstation_leader_log.toggle_star",
            args: { docname: docname, state: is_on ? 'off' : 'on' },
            // If the server throws an error (frappe.throw)
            error: function(r) {
                // Revert the star back immediately
                $wrapper.attr('data-starred', is_on ? 'true' : 'false');

                frappe.msgprint({
                    title: __('Authorization Required'),
                    indicator: 'red',
                    message: __('You cannot save this because no Workstation Leader is assigned to your Employee profile.')
                });
            }
        });
    } catch (e) {
        console.error("Star Toggle Action Error:", e);
    }
};