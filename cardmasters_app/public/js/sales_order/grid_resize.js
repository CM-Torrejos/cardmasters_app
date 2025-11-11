frappe.ui.form.on('Sales Order', {
    refresh: function(frm) {
        
        // --- THIS IS YOUR DYNAMIC LIST ---
        const trigger_fields = [
            'custom_item_specifics',
            'custom_particulars'
        ];

        // --- Helper function for height ---
        const setImportantHeight = (element, height) => {
            element.style.setProperty('height', height, 'important');
        };

        // --- Helper function for placeholder centering ---
        const centerEmptyPlaceholders = ($row, newHeight) => {
            const placeholderLineHeight = 16; // avg px height of one line of text
            let newPaddingTop = (parseInt(newHeight, 10) - placeholderLineHeight) / 2;
            if (newPaddingTop < 0) newPaddingTop = 0;

            $row.find('textarea').each(function() {
                let $el = $(this);
                // $el.css('text-align', 'center'); // You had this commented, so I'll keep it commented.

                if ($el.val() === '') {
                    $el.css('padding-top', newPaddingTop + 'px');
                } else {
                    $el.css('padding-top', '');
                    $el.css('text-align', '');
                }
            });
        };
        
        // --- [NEW FUNCTION] Finds the tallest field ---
        const getTallestHeight = ($row, fieldnames) => {
            let tallest = 0;

            fieldnames.forEach(fieldname => {
                let $field = $row.find(`textarea[data-fieldname="${fieldname}"]`);
                if ($field.length) {
                    // Temporarily set height to auto to measure
                    $field.css('height', 'auto'); 
                    
                    let scrollHeight = $field.get(0).scrollHeight;
                    if (scrollHeight > tallest) {
                        tallest = scrollHeight;
                    }
                }
            });
            return (tallest + 2) + 'px'; // Return the max height with buffer
        };

        // --- Dynamic Selector Builder ---
        const trigger_selector = trigger_fields
            .map(fieldname => `textarea[data-fieldname="${fieldname}"]`)
            .join(', ');

        // Find the grid's main container
        let grid_wrapper = frm.fields_dict.items.grid.wrapper;

        // --- Updated Listener ---
        $(grid_wrapper).on(
            'input', 
            trigger_selector, 
            function() {
                // 'this' is the element we're typing in
                let trigger_element = this;
                
                setTimeout(() => {
                    // Find the parent row *first*
                    let $row = $(trigger_element).closest('.data-row');

                    // --- [FIXED LOGIC] ---
                    // 1. Find the tallest height needed for ANY trigger field in this row
                    let newHeight = getTallestHeight($row, trigger_fields);
                    
                    // 2. Resize all form controls
                    $row.find('.form-control').each(function() {
                        setImportantHeight(this, newHeight);
                    });
                    
                    // 3. Resize the Row-Index and Row-Check columns
                    $row.find('.row-index.sortable-handle.col').each(function() {
                        setImportantHeight(this, newHeight);
                    });
                    $row.find('.row-check.sortable-handle.col').each(function() {
                        setImportantHeight(this, newHeight);
                    });

                    // 4. Resize the "Edit" button's column
                    $row.find('.col:last-child').each(function() {
                        setImportantHeight(this, newHeight);
                    });
                    
                    // 5. Center placeholders in empty fields
                    centerEmptyPlaceholders($row, newHeight);

                }, 0); // Only one timeout needed now
            }
        );
    }
});