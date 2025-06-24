frappe.provide('frappe.ui.form');

frappe.ui.form.ContactQEntry = class ContactQEntry extends frappe.ui.form.QuickEntryForm{
    constructor(doctype, after_insert, init_callback, doc, force) {
		super(doctype, after_insert, init_callback, doc, force);
		this.skip_redirect_on_error = true;
	}

	render_dialog() {
		this.mandatory = this.mandatory.concat(this.get_variant_fields());
		super.render_dialog();
	}

	insert() {
		/**
		 * Using alias fieldnames because the doctype definition define "email_id" and "mobile_no" as readonly fields.
		 * Therefor, resulting in the fields being "hidden".
		 */
		const map_field_names = {
			email_address: "email_id",
			mobile_number: "mobile_no",
		};

		Object.entries(map_field_names).forEach(([fieldname, new_fieldname]) => {
			this.dialog.doc[new_fieldname] = this.dialog.doc[fieldname];
			delete this.dialog.doc[fieldname];
		});

		return super.insert();
	}

    get_variant_fields() {
        var variant_fields = [{
            fieldtype: "Section Break",
            label: __("Primary Contact Details"),
            collapsible: 1
        },
        {
            label: __("Email Id"),
            fieldname: "email_address",
            fieldtype: "Data",
            options: "Email",
            reqd: 1
        },
        {
            fieldtype: "Column Break"
        },
        {
            label: __("Mobile Number"),
            fieldname: "mobile_number",
            fieldtype: "Data",
            reqd: 1
        },
        {
            fieldtype: "Section Break",
            label: __("Primary Address Details"),
            collapsible: 1
        },
        {
            label: __("Address Line 1"),
            fieldname: "address_line1",
            fieldtype: "Data",
            reqd: 1
        },
        {
            label: __("Address Line 2"),
            fieldname: "address_line2",
            fieldtype: "Data"
        },
        {
            label: __("ZIP Code"),
            fieldname: "pincode",
            fieldtype: "Data",
            reqd: 1,
            default: "Cagayan De Oro City"
        },
        {
            fieldtype: "Column Break"
        },
        {
            label: __("Country"),
            fieldname: "country",
            fieldtype: "Link",
            options: "Country",
            default: frappe.sys_defaults.country
        },
        {
            label: __("City"),
            fieldname: "city",
            fieldtype: "Link",
            reqd: 1,
            default: "Cagayan De Oro City"
        },
        {
            label: __("State"),
            fieldname: "state",
            fieldtype: "Link",
        },
        {
            label: __("Customer POS Id"),
            fieldname: "customer_pos_id"    ,
            fieldtype: "Data",
            hidden: 1
        }];
    
        return variant_fields;
    }
    
}

frappe.ui.form.ContactAddressQuickEntryForm = frappe.ui.form.ContactQEntry;
frappe.ui.form.CustomerQuickEntryForm       = frappe.ui.form.ContactQEntry;