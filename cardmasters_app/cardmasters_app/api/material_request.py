import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc


@frappe.whitelist()
def update_details(material_request, items, modified, confirm_work_orders=False):
    from cardmasters_app.cardmasters_app.services.material_request import update_material_request_details

    return update_material_request_details(material_request, items, modified, confirm_work_orders)


@frappe.whitelist()
def make_batched_material_transfer(source_name, target_doc=None):
    """Prepare an unsaved batched Material Transfer from a submitted Material Request."""

    def include_item(source):
        return bool(frappe.get_cached_value("Item", source.item_code, "is_stock_item"))

    def map_item(source, target, source_parent):
        from cardmasters_app.cardmasters_app.services.batch_handler import (
            get_batch_source_warehouse,
            resolve_material_request_batch,
        )

        target.qty = source.qty
        target.conversion_factor = source.conversion_factor or 1
        target.transfer_qty = target.qty * target.conversion_factor
        target.material_request = source_parent.name
        target.material_request_item = source.name
        target.s_warehouse = source.from_warehouse
        target.t_warehouse = source.warehouse
        target.use_serial_batch_fields = 1

        if frappe.get_cached_value("Item", source.item_code, "has_batch_no"):
            target.batch_no = resolve_material_request_batch(
                source_parent.name,
                source.name,
                source.item_code,
            )
            target.s_warehouse = get_batch_source_warehouse(
                target.batch_no,
                target.transfer_qty,
                source_parent.company,
            )

    def set_defaults(source, target):
        target.purpose = "Material Transfer"
        target.set_stock_entry_type()
        target.company = source.company
        target.from_warehouse = None
        target.to_warehouse = source.set_warehouse
        if target.meta.has_field("custom_sales_order"):
            target.custom_sales_order = source.get("custom_sales_order")
        target.set_missing_values()

    stock_entry = get_mapped_doc(
        "Material Request",
        source_name,
        {
            "Material Request": {
                "doctype": "Stock Entry",
                "validation": {"docstatus": ["=", 1]},
            },
            "Material Request Item": {
                "doctype": "Stock Entry Detail",
                "condition": include_item,
                "field_map": {
                    "name": "material_request_item",
                    "parent": "material_request",
                    "uom": "stock_uom",
                },
                "field_no_map": ["expense_account"],
                "postprocess": map_item,
            },
        },
        target_doc,
        set_defaults,
    )

    if not stock_entry.items:
        frappe.throw(
            _("Material Request {0} has no stock items to transfer.").format(source_name)
        )

    return stock_entry
