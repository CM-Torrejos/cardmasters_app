frappe.provide('frappe.ui.form');

frappe.ui.form.CustomerQEntryWithPerson = class CustomerQEntryWithPerson extends frappe.ui.form.QuickEntryForm {
	constructor(doctype, after_insert, init_callback, doc, force) {
		super(doctype, after_insert, init_callback, doc, force);
		this.skip_redirect_on_error = true;
	}

	render_dialog() {
		this.mandatory = this.mandatory.concat(this.get_variant_fields());
		super.render_dialog();
	}

	// Save customer, then apply first/last name to the primary Contact (update or create).
	insert() {
		// alias map used so email/mobile show even if the base fields are readonly in doctype
		const map_field_names = {
			email_address: "email_id",
			mobile_number: "mobile_no",
		};

		Object.entries(map_field_names).forEach(([fieldname, new_fieldname]) => {
			this.dialog.doc[new_fieldname] = this.dialog.doc[fieldname];
			delete this.dialog.doc[fieldname];
		});

		// Keep the name pieces around for after-insert contact handling
		const first_name = (this.dialog.doc.first_name || "").trim();
		const last_name  = (this.dialog.doc.last_name  || "").trim();
		const email_id   = (this.dialog.doc.email_id   || "").trim();
		const mobile_no  = (this.dialog.doc.mobile_no  || "").trim();

		return super.insert().then((r) => {
			const customer = r?.doc || r;
			const customer_name = customer?.name;

			// nothing extra to do if user didn’t enter a person name
			if (!first_name && !last_name) return r;

			// Try to update the primary contact if one was auto-created.
			// In recent ERPNext versions this lives on customer.customer_primary_contact
			const get_primary = () =>
				frappe.db.get_value('Customer', customer_name, 'customer_primary_contact')
					.then(res => res?.message?.customer_primary_contact);

			const update_contact = (contact_name) => {
				if (!contact_name) return Promise.resolve(null);
				return frappe.call({
					method: "frappe.client.set_value",
					args: {
						doctype: "Contact",
						name: contact_name,
						fieldname: {
							first_name: first_name || undefined,
							last_name:  last_name  || undefined
						}
					}
				}).then(() => contact_name);
			};

			const create_contact = () => {
				const contact_doc = {
					doctype: "Contact",
					first_name: first_name || undefined,
					last_name: last_name || undefined,
					links: [{
						link_doctype: "Customer",
						link_name: customer_name,
					}],
				};

				// Populate primary email/phone if provided
				if (email_id) {
					contact_doc.email_ids = [{ email_id, is_primary: 1 }];
				}
				if (mobile_no) {
					contact_doc.phone_nos = [{ phone: mobile_no, is_primary_mobile_no: 1, is_primary_phone: 1 }];
				}

				return frappe.call({
					method: "frappe.client.insert",
					args: { doc: contact_doc }
				});
			};

			return get_primary()
				.then(primary_name => {
					if (primary_name) {
						// Update existing auto-created contact so we don’t make duplicates
						return update_contact(primary_name);
					}
					// No primary contact? create one linked to this Customer
					return create_contact();
				})
				.then(() => r);
		});
	}

	get_variant_fields() {
		const variant_fields = [


			// ------- your existing contact/address sections --------
			{
				fieldtype: "Section Break",
				label: __("Primary Contact Details"),
				collapsible: 1
			},
            
			{ fieldtype: "Column Break"},

			{
				label: __("Email Id"),
				fieldname: "email_address",
				fieldtype: "Data",
				options: "Email",
				reqd: 1
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
			{ fieldtype: "Column Break" },
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
				fieldtype: "Data",
				reqd: 1,
				default: "Cagayan De Oro City"
			},
			{
				label: __("State/Province"),
				fieldname: "state",
				fieldtype: "Data",
				default: "Misamis Oriental"
			},
			{
				label: __("Customer POS Id"),
				fieldname: "customer_pos_id",
				fieldtype: "Data",
				hidden: 1
			}
		];

		return variant_fields;
	}
};

// Wire up our subclass for both quick entry aliases
frappe.ui.form.ContactAddressQuickEntryForm = frappe.ui.form.CustomerQEntryWithPerson;
frappe.ui.form.CustomerQuickEntryForm = frappe.ui.form.CustomerQEntryWithPerson;
