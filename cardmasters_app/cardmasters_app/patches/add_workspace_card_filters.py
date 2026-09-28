from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({"Workspace Link": [{
        "fieldname": "custom_card_filters",
        "label": "Card Link Filters",
        "fieldtype": "Code",
        "options": "JSON",
        "insert_after": "link_to",
        "depends_on": 'eval:doc.type == "Link" && doc.link_type == "DocType"',
        "description": "Use Edit Link Filters in the workspace card editor to configure these filters.",
    }, {
        "fieldname": "custom_card_show_count",
        "label": "Show Result Count",
        "fieldtype": "Check",
        "default": "0",
        "insert_after": "custom_card_filters",
        "depends_on": 'eval:doc.type == "Link" && doc.link_type == "DocType"',
    }, {
        "fieldname": "custom_card_count_color",
        "label": "Count Color",
        "fieldtype": "Select",
        "options": "Grey\nGreen\nRed\nOrange\nPink\nYellow\nBlue\nCyan",
        "default": "Grey",
        "insert_after": "custom_card_show_count",
        "depends_on": 'eval:doc.type == "Link" && doc.link_type == "DocType" && doc.custom_card_show_count',
    }]}, update=True)
