frappe.listview_settings["Artist Card"] = {
    onload: function(listview) {
        // Initialize a tracker for the last synced value
        listview.last_synced_artist = null;

        const original_get_args = listview.get_args;
        
        listview.get_args = function() {
            let args = original_get_args.call(this);

            // Find the filter
            let custom_filter = args.filters.find(f => f[1] === "any_artist_search");
            let artist_value = custom_filter ? custom_filter[3] : "";

            // Only call the server if the value changed
            // This prevents the API call on simple actions like Sorting or Pagination
            if (listview.last_synced_artist !== artist_value) {
                frappe.call({
                    method: "cardmasters_app.cardmasters_app.api.artist_card.artist_filter_listview.set_search_session",
                    args: { artist: artist_value },
                    async: false, // Blocking call is necessary here
                    freeze: false
                });

                // Update our tracker
                listview.last_synced_artist = artist_value;
            }

            // SCRUB the filter so the DB doesn't see it
            args.filters = args.filters.filter(f => f[1] !== "any_artist_search");

            return args;
        };
    }
};