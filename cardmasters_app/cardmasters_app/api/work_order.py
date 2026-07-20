import frappe

@frappe.whitelist()
def update_work_order_details(docname, qty, item_specifics=None, particulars=None, operations=None):
    from cardmasters_app.cardmasters_app.services.work_order import update_work_order_details as update_details
    return update_details(docname, qty, item_specifics, particulars, operations)

@frappe.whitelist()
def get_current_employee_workstations():
    from cardmasters_app.cardmasters_app.services.work_order import get_current_employee_workstations as get_workstations
    return get_workstations()

@frappe.whitelist()
def get_workstation_completion_options(docname, action=None):
    from cardmasters_app.cardmasters_app.services.work_order import get_workstation_completion_options as get_options
    return get_options(docname, action)

@frappe.whitelist()
def mark_workstation_jobs_complete(docname, workstation):
    from cardmasters_app.cardmasters_app.services.work_order import mark_workstation_jobs_complete as mark_complete
    return mark_complete(docname, workstation)

@frappe.whitelist()
def undo_workstation_jobs_complete(docname, workstation):
    from cardmasters_app.cardmasters_app.services.work_order import undo_workstation_jobs_complete as undo_complete
    return undo_complete(docname, workstation)

@frappe.whitelist()
def get_linked_stock_work_orders(docname):
    from cardmasters_app.cardmasters_app.services.work_order import get_linked_stock_work_orders as get_linked
    return get_linked(docname)

@frappe.whitelist()
def get_damages_and_returns_defaults(docname):
    from cardmasters_app.cardmasters_app.services.work_order import get_damages_and_returns_defaults as get_defaults
    return get_defaults(docname)

@frappe.whitelist()
def get_repack_damage_stock_entry_defaults(docname):
    from cardmasters_app.cardmasters_app.services.work_order import get_repack_damage_stock_entry_defaults as get_defaults
    return get_defaults(docname)

@frappe.whitelist()
def get_sales_order_item_work_order_defaults(so_detail):
    if not so_detail:
        return {}

    return frappe.db.get_value(
        "Sales Order Item",
        so_detail,
        ["bom_no", "custom_item_specifics", "custom_particulars"],
        as_dict=True,
    ) or {}

@frappe.whitelist()
def get_material_request_item_work_order_defaults(material_request, material_request_item):
    if not material_request or not material_request_item:
        return {}

    mr = frappe.get_doc("Material Request", material_request)
    mr.check_permission("read")

    row = next((item for item in mr.items if item.name == material_request_item), None)
    if not row:
        frappe.throw("Material Request Item row was not found.")

    default_wip_warehouse = frappe.db.get_single_value(
        "Manufacturing Settings", "default_wip_warehouse"
    )
    bom_no = frappe.db.get_value(
        "BOM",
        {
            "item": row.item_code,
            "is_default": 1,
            "docstatus": 1,
        },
        "name",
    )
    sales_order_customer = None
    if row.get("sales_order"):
        sales_order_customer = frappe.db.get_value("Sales Order", row.sales_order, "customer")

    has_batch = bool(row.get("batch_no")) or bool(
        frappe.db.get_value("Item", row.item_code, "has_batch_no")
    )

    return {
        "company": mr.company,
        "transaction_date": mr.transaction_date,
        "material_request_type": mr.material_request_type,
        "item_code": row.item_code,
        "item_name": row.item_name,
        "qty": row.stock_qty - row.ordered_qty,
        "fg_warehouse": row.warehouse,
        "wip_warehouse": default_wip_warehouse,
        "description": row.description,
        "stock_uom": row.stock_uom,
        "expected_delivery_date": row.schedule_date,
        "sales_order": row.get("sales_order"),
        "sales_order_item": row.get("sales_order_item"),
        "bom_no": bom_no,
        "material_request": mr.name,
        "material_request_item": row.name,
        "project": row.project,
        "custom_item_specifics": row.get("custom_item_specifics"),
        "custom_customer": sales_order_customer,
        "custom_production_type": "Make to Order (Internal)" if has_batch else "Make to Stock",
    }
