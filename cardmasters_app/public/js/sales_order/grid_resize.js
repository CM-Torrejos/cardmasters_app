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

        // --- [NEW] Helper function for placeholder centering ---
        const centerEmptyPlaceholders = ($row, newHeight) => {
            // Estimate placeholder line height (adjust if needed)
            const placeholderLineHeight = 16; // avg px height of one line of text
            
            // Calculate the padding needed
            let newPaddingTop = (parseInt(newHeight, 10) - placeholderLineHeight) / 2;
            
            // Ensure padding isn't negative
            if (newPaddingTop < 0) newPaddingTop = 0;

            // Find all textareas in the row
            $row.find('textarea').each(function() {
                let $el = $(this);
                
                // Horizontally center the placeholder
                // $el.css('text-align', 'center');

                // If the textarea is empty (it's the placeholder)
                if ($el.val() === '') {
                    // Apply the dynamic padding
                    $el.css('padding-top', newPaddingTop + 'px');
                } else {
                    // If it has text, reset padding to normal
                    $el.css('padding-top', ''); // or your default, e.g., '10px'
                    $el.css('text-align', ''); // Reset text-align
                }
            });
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
                let trigger_element = this;
                
                setTimeout(() => {
                    setImportantHeight(trigger_element, 'auto');
                    
                    setTimeout(() => {
                        let newHeight = (trigger_element.scrollHeight + 2) + 'px';
                        
                        // 1. Set the height of the element we typed in
                        setImportantHeight(trigger_element, newHeight);
                        
                        let $row = $(trigger_element).closest('.data-row');
                        
                        // 2. Resize all OTHER form controls
                        $row.find('.form-control').not(trigger_element).each(function() {
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
                        
                        // 5. [NEW] Center placeholders in empty fields
                        centerEmptyPlaceholders($row, newHeight);

                    }, 0);
                }, 0);
            }
        );
    }
});