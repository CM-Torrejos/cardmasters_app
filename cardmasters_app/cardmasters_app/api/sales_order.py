import frappe
from frappe import _
from frappe.model.mapper import get_mapped_doc
import json


@frappe.whitelist()
def get_current_user_employee_branch():
    """Return the branch from the Employee record linked to the current user."""
    if frappe.session.user in ("Administrator", "Guest"):
        return None

    return (
        frappe.db.get_value(
            "Employee",
            {
                "user_id": frappe.session.user,
                "status": "Active",
            },
            "branch",
        )
        or frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "branch")
    )


@frappe.whitelist()
def make_batched_material_transfer(source_name, target_doc=None):
    """Prepare an unsaved Material Transfer from a submitted Sales Order."""
    def include_item(source):
        return bool(frappe.get_cached_value("Item", source.item_code, "is_stock_item"))

    def map_item(source, target, source_parent):
        target.qty = source.qty
        target.conversion_factor = source.conversion_factor or 1
        target.transfer_qty = target.qty * target.conversion_factor
        target.use_serial_batch_fields = 1

        if frappe.get_cached_value("Item", source.item_code, "has_batch_no"):
            from cardmasters_app.cardmasters_app.services.batch_handler import (
                get_batch_source_warehouse,
                resolve_sales_order_batch,
            )

            target.batch_no = resolve_sales_order_batch(
                source_parent.name,
                source.name,
                source.item_code,
                source.get("custom_item_specifics"),
            )
            target.s_warehouse = get_batch_source_warehouse(
                target.batch_no, target.transfer_qty, source_parent.company
            )

    def set_defaults(source, target):
        target.purpose = "Material Transfer"
        target.set_stock_entry_type()
        target.company = source.company
        target.custom_sales_order = source.name
        target.to_warehouse = None
        target.set_missing_values()

    stock_entry = get_mapped_doc(
        "Sales Order",
        source_name,
        {
            "Sales Order": {
                "doctype": "Stock Entry",
                "validation": {"docstatus": ["=", 1]},
            },
            "Sales Order Item": {
                "doctype": "Stock Entry Detail",
                "condition": include_item,
                "postprocess": map_item,
            },
        },
        target_doc,
        set_defaults,
    )

    if not stock_entry.items:
        frappe.throw(_("Sales Order {0} has no stock items to transfer.").format(source_name))

    return stock_entry

@frappe.whitelist()
def make_quotation_from_so(source_name):
    # Create the Quotation using the mapper
    target_doc = get_mapped_doc("Sales Order", source_name, {
        "Sales Order": {
            "doctype": "Quotation",
            "field_map": {
                "customer": "party_name",
                "customer_name": "customer_name",
                "name": "custom_sales_order_ref"
            }
        },
        "Sales Order Item": {
            "doctype": "Quotation Item",
        }
    })

    # Set mandatory Quotation fields
    target_doc.quotation_to = "Customer"
    
    return target_doc

@frappe.whitelist()
def create_project_for_sales_order(project_name):
    """
    Creates a Project document server-side so that all before_insert/after_insert
    hooks on Project fire correctly. Returns the new Project name.
    """
    if not project_name:
        frappe.throw("Project name is required.")

    project = frappe.new_doc("Project")
    project.project_name = project_name
    project.insert()
    return project.name


@frappe.whitelist()
def check_wo_discrepancy(so_name, items):
    if not so_name:
        return None
        
    # Parse the incoming JSON items from the frontend
    current_items = json.loads(items)
    current_items_map = {item.get("name"): item for item in current_items if item.get("name")}
    
    # Fetch the original items from the database BEFORE the save commits
    old_items = frappe.get_all(
        "Sales Order Item", 
        filters={"parent": so_name}, 
        fields=["name", "item_code", "custom_item_specifics", "custom_particulars"]
    )
    
    discrepancy_messages = []
    
    for old_item in old_items:
        current_item = current_items_map.get(old_item.name)
        if not current_item:
            continue
            
        # Safely get old and new values, defaulting to empty strings if None
        old_specifics = old_item.custom_item_specifics or ""
        new_specifics = current_item.get("custom_item_specifics") or ""
        
        old_particulars = old_item.custom_particulars or ""
        new_particulars = current_item.get("custom_particulars") or ""
        
        # Check if either field was modified
        if old_specifics != new_specifics or old_particulars != new_particulars:
            
            # Look for linked Work Orders that are not cancelled
            work_orders = frappe.get_all(
                "Work Order", 
                filters={
                    "sales_order": so_name, 
                    "sales_order_item": old_item.name, 
                    "docstatus": ["<", 2] 
                },
                fields=["name"]
            )
            
            # Format the string for each Work Order found
            for wo in work_orders:
                msg = f"<b>{wo.name}</b> - {old_item.item_code}<br>"
                if old_specifics != new_specifics:
                    msg += f"Item specifics: {old_specifics} &rarr; {new_specifics}<br>"
                if old_particulars != new_particulars:
                    msg += f"Particulars: {old_particulars} &rarr; {new_particulars}<br>"
                    
                discrepancy_messages.append(msg)
                
    # If we found discrepancies, build the final HTML message
    if discrepancy_messages:
        header = "The following changes will cause a discrepancy in the linked work orders.<br><br>Please immediately contact the work order authors to update the details of the work orders as below:<br><br>"
        body = "<br>".join(discrepancy_messages)
        footer = "<br><br>If discrepancies are found by the time of consumption, damages will be charged to the sales order owner. Proceed?"
        return header + body + footer
        
    return None

@frappe.whitelist()
def update_custom_child_fields(parent_doctype, trans_items, parent_doctype_name, child_docname="items", new_project_name=None):
    from erpnext.controllers.accounts_controller import update_child_qty_rate 
    # BULLETPROOFING: Frappe sometimes parses arrays automatically from the frontend.
    # The standard core function strictly expects a string. We ensure both forms exist.
    if isinstance(trans_items, list):
        data = trans_items
        trans_items_str = json.dumps(trans_items)
    else:
        data = json.loads(trans_items)
        trans_items_str = trans_items

    # STEP 1: Let standard ERPNext handle all Qty, Rate, Stock, and GL logic safely
    # (Pass the stringified version)
    update_child_qty_rate(parent_doctype, trans_items_str, parent_doctype_name, child_docname)

    # STEP 2: Setup table name
    child_table = f"{parent_doctype} Item"

    # STEP 3: Save ONLY our custom fields directly to the database
    for row in data:
        if row.get("docname"):
            frappe.db.set_value(
                child_table,
                row.get("docname"),
                {
                    "custom_item_specifics": row.get("custom_item_specifics"),
                    "custom_particulars": row.get("custom_particulars")
                },
                update_modified=False # Prevents unnecessary validation loops
            )
            
    # STEP 4: Forcefully bypass submission locks to link the newly created project
    if new_project_name and parent_doctype == "Sales Order":
        frappe.db.sql("""
            UPDATE `tabSales Order` 
            SET project = %s 
            WHERE name = %s
        """, (new_project_name, parent_doctype_name), auto_commit=1)
    
    # STEP 5: Update the parent document's timestamp so the UI knows it was refreshed
    frappe.db.set_value(parent_doctype, parent_doctype_name, "modified", frappe.utils.now())

@frappe.whitelist()
def get_sales_order_html(sales_order_name):
    if not sales_order_name:
        return ""

    if not frappe.db.exists("Sales Order", sales_order_name):
        return ""

    try:
        print_format = get_default_print_format("Sales Order")

        html = frappe.get_print(
            doctype="Sales Order",
            name=sales_order_name,
            print_format=print_format,
            as_pdf=False,
        )
        return html
    except Exception as e:
        frappe.log_error(f"Error generating Sales Order HTML: {e}")
        return "<div>Error loading Sales Order</div>"

def get_default_print_format(doctype):
    meta = frappe.get_meta(doctype)

    if meta.default_print_format:
        return meta.default_print_format
    
    return meta.default_print_format or "Standard"

@frappe.whitelist()
def get_sales_order_outstanding(so_name):
    from cardmasters_app.cardmasters_app.services.outstanding_balance import get_sales_order_outstanding as get_outstanding
    return get_outstanding(so_name)


@frappe.whitelist()
def get_customer_sales_order_outstanding(customer, company):
    """Sum submitted Sales Order balances visible to the current user."""
    if not customer or not company:
        return 0

    sales_orders = frappe.get_list(
        "Sales Order",
        filters={
            "customer": customer,
            "company": company,
            "docstatus": 1,
            "custom_outstanding_balance": [">", 0],
        },
        fields=["custom_outstanding_balance"],
        limit_page_length=0,
    )

    return sum(sales_order.custom_outstanding_balance or 0 for sales_order in sales_orders)


@frappe.whitelist()
def get_customer_dashboard_balance(customer, company):
    """Return the same company balance shown in the Customer dashboard Stats section."""
    if not customer or not company:
        return None

    customer_doc = frappe.get_doc("Customer", customer)
    customer_doc.check_permission("read")

    from erpnext.accounts.party import get_dashboard_info

    # ERPNext returns None when the user cannot read the party's invoice DocType.
    dashboard_info = get_dashboard_info("Customer", customer, customer_doc.loyalty_program) or []
    return next((info for info in dashboard_info if info.get("company") == company), None)
