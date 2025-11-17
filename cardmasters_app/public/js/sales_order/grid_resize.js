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
            const placeholderLineHeight = 16; 
            let newPaddingTop = (parseInt(newHeight, 10) - placeholderLineHeight) / 2;
            if (newPaddingTop < 0) newPaddingTop = 0;

            $row.find('textarea').each(function() {
                let $el = $(this);
                // $el.css('text-align', 'center'); 

                if ($el.val() === '') {
                    $el.css('padding-top', newPaddingTop + 'px');
                } else {
                    $el.css('padding-top', '');
                    $el.css('text-align', '');
                }
            });
        };
        
        // --- Finds the tallest field ---
        const getTallestHeight = ($row, fieldnames) => {
            let tallest = 0;
            fieldnames.forEach(fieldname => {
                let $field = $row.find(`textarea[data-fieldname="${fieldname}"]`);
                if ($field.length) {
                    // This 'auto' reset is key to measuring
                    $field.css('height', 'auto'); 
                    let scrollHeight = $field.get(0).scrollHeight;
                    if (scrollHeight > tallest) {
                        tallest = scrollHeight;
                    }
                }
            });
            let minHeight = 62; // Your CSS minimum
            if (tallest < minHeight) tallest = minHeight;
            
            return (tallest + 2) + 'px'; // Return the max height with buffer
        };
        
        // --- MASTER RESIZE FUNCTION (No changes) ---
        const resizeRow = ($dataRow) => {
            // Check if the row still exists in the DOM
            if (!$dataRow || !$dataRow.length) return; 

            let newHeight = getTallestHeight($dataRow, trigger_fields);
            
            $dataRow.find('.form-control').each(function() {
                setImportantHeight(this, newHeight);
            });
            
            $dataRow.find('.row-index.sortable-handle.col').each(function() {
                setImportantHeight(this, newHeight);
            });
            $dataRow.find('.row-check.sortable-handle.col').each(function() {
                setImportantHeight(this, newHeight);
            });

            $dataRow.find('.col:last-child').each(function() {
                setImportantHeight(this, newHeight);
            });
            
            centerEmptyPlaceholders($dataRow, newHeight);

            let $gridRow = $dataRow.closest('.grid-row');
            if ($gridRow.length) {
                $gridRow.css('min-height', newHeight);
            }
        };

        // --- DYNAMIC SELECTOR AND GRID WRAPPER ---
        const trigger_selector = trigger_fields
            .map(fieldname => `textarea[data-fieldname="${fieldname}"]`)
            .join(', ');
            
        let grid_wrapper = frm.fields_dict.items.grid.wrapper;

        // --- LISTENER 1 (For Typing) ---
        // This is fast and has no delay.
        $(grid_wrapper).on(
            'input', 
            trigger_selector, 
            function() {
                let $dataRow = $(this).closest('.data-row');
                resizeRow($dataRow); // No timeout needed, fires as you type
            }
        );

        // --- [THE FIX] LISTENER 2 (For Clicking) ---
        // This listens for *any* field getting focus and
        // uses a 50ms delay to wait for Frappe to render.
        $(grid_wrapper).on(
            'focusin',
            '.form-control', // This fires on the "first click"
            function() {
                let $dataRow = $(this).closest('.data-row');
                
                // Only run this if it's an editable row
                if ($dataRow.hasClass('editable-row')) {
                    // Use a 50ms delay to wait for all fields
                    // to be rendered in the DOM before we measure them.
                    setTimeout(() => resizeRow($dataRow), 50);
                }
            }
        );
    }
});