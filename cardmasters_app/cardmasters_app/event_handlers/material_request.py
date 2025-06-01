def stock_entry_before_insert(doc, method):
    """
    Hook: before_insert on Stock Entry.
    If this Stock Entry was generated from a Material Request, fetch that MR,
    take its first item row’s `sales_order` value, and populate doc.custom_sales_order.
    """
    # Only proceed if this Stock Entry is linked to a Material Request
    mr_name = doc.get("material_request")
    if not mr_name:
        return

    try:
        mr = frappe.get_doc("Material Request", mr_name)
    except frappe.DoesNotExistError:
        # If the MR was deleted or invalid, just skip
        return

    if mr.items:
        first_item = mr.items[0]
        so_name = first_item.get("sales_order")
        if so_name:
            # Assume `custom_sales_order` is your custom Data/Link field on Stock Entry
            doc.custom_sales_order = so_name