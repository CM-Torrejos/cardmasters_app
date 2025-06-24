frappe.provide('frappe.ui.form');

frappe.ui.form.ContactQEntry = class ContactQEntry extends frappe.ui.form.QuickEntryForm{
    render_dialog() {
        this.mandatory = this.mandatory.concat(this.get_variant_fields());
        super.render_dialog();
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
            default: "9000"
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