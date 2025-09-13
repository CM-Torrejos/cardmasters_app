frappe.ui.form.on('Employee', {
    validate: function(frm) {
        if (frm.doc.date_of_joining && frm.doc.date_of_birth) {

            // Parse date_of_birth into mmddyy format
            let dob = frappe.datetime.str_to_obj(frm.doc.date_of_birth);
            let mm = String(dob.getMonth() + 1).padStart(2, '0'); // months are 0-based
            let dd = String(dob.getDate()).padStart(2, '0');
            let yy = dob.getFullYear().toString().slice(-2);

            // Combine into the desired format: CM{YY}-{MMDDYY}
            frm.set_value('custom_id_code', `${mm}${dd}${yy}`);
        }
    }
});
