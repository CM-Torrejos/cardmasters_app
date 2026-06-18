import frappe
import json


def execute():
    remove_custom_starred_by_from_field_order()

    if frappe.db.exists("Custom Field", "Work Order-custom_starred_by"):
        frappe.delete_doc("Custom Field", "Work Order-custom_starred_by", force=True)

    if frappe.db.exists("DocType", "Workstation Leader Log"):
        frappe.delete_doc("DocType", "Workstation Leader Log", force=True)

    frappe.clear_cache(doctype="Work Order")


def remove_custom_starred_by_from_field_order():
    property_setter = "Work Order-main-field_order"
    field_order = frappe.db.get_value("Property Setter", property_setter, "value")
    if not field_order or "custom_starred_by" not in field_order:
        return

    try:
        fields = json.loads(field_order)
    except ValueError:
        return

    fields = [field for field in fields if field != "custom_starred_by"]
    frappe.db.set_value("Property Setter", property_setter, "value", json.dumps(fields))
