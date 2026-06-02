import frappe
from frappe import _

@frappe.whitelist()
def make_rcpi_stock_entry(material_request_name):
    """
    Create a draft Stock Entry of type 'Material Receipt' from a Customer-Provided Material Request.
    Returns the new Stock Entry's name.
    """
    # 1. Load the Material Request
    mr = frappe.get_doc("Material Request", material_request_name)

    # 2. Validate that this MR is indeed a 'Customer Provided' type
    if mr.material_request_type != "Customer Provided":
        frappe.throw(_("Material Request {0} is not of type 'Customer Provided'.").format(material_request_name))

    # 3. Create a new Stock Entry document in memory
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"

    # If you want to capture the related Sales Order (from the first child row)
    # (this assumes every MR item has a sales_order field populated)
    if mr.items and mr.items[0].sales_order:
        se.custom_sales_order = mr.items[0].sales_order

    # 4. Map each child row of MR → Stock Entry Detail
    for row in mr.items:
        # Only map those rows that came from this MR (you could add more filtering here if needed)
        se.append("items", {
            "item_code":                 row.item_code,
            "qty":                       row.qty,
            "uom":                       row.uom,
            "stock_uom":                 row.stock_uom,
            "transfer_qty":              row.qty,
            "t_warehouse":               row.warehouse,
            "material_request":          mr.name,
            "material_request_item":     row.name,
            "basic_rate":                '0',
            "custom_item_specifics":     row.get("custom_item_specifics"),
            "use_serial_batch_fields":   1
        })

    # 5. Insert the Stock Entry (so it’s now a draft in the DB)
    se.insert(ignore_permissions=True)

    # 6. Return the new Stock Entry name so the client can redirect
    return se.name

@frappe.whitelist()
def make_finish_stock_entry(material_request_name):
    """
    Create a draft Stock Entry of type 'Material Receipt' from a Customer-Provided Material Request.
    Returns the new Stock Entry's name.
    """
    # 1. Load the Material Request
    mr = frappe.get_doc("Material Request", material_request_name)

    # 2. Validate that this MR is indeed a 'Customer Provided' type
    if mr.material_request_type != "Customer Provided":
        frappe.throw(_("Material Request {0} is not of type 'Customer Provided'.").format(material_request_name))

    # 3. Create a new Stock Entry document in memory
    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Receipt"

    # If you want to capture the related Sales Order (from the first child row)
    # (this assumes every MR item has a sales_order field populated)
    if mr.items and mr.items[0].sales_order:
        se.custom_sales_order = mr.items[0].sales_order

    # 4. Map each child row of MR → Stock Entry Detail
    for row in mr.items:
        # Only map those rows that came from this MR (you could add more filtering here if needed)
        se.append("items", {
            "item_code":                 row.item_code,
            "qty":                       row.qty,
            "uom":                       row.uom,
            "stock_uom":                 row.stock_uom,
            "transfer_qty":              row.qty,
            "t_warehouse":               row.warehouse,
            "material_request":          mr.name,
            "material_request_item":     row.name,
            "basic_rate":                0,
            "custom_item_specifics":     row.get("custom_item_specifics"),
            "use_serial_batch_fields":   1
        })

    # 5. Insert the Stock Entry (so it’s now a draft in the DB)
    se.insert(ignore_permissions=True)

    # 6. Return the new Stock Entry name so the client can redirect
    return se.name
