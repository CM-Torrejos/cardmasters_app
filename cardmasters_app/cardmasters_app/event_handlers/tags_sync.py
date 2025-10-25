import frappe

def copy_tags_from_sales_order(doc, method):
    """
    Hook: Work Order - after_insert
    Action: Pulls tags from the linked Sales Order when a new Work Order is created.
    'doc' is the new Work Order document.
    """
    
    # Use .error() for high-visibility logging
    frappe.logger().error(f"[Tag Sync] HOOK 'after_insert' running for WO: {doc.name}")

    if not doc.sales_order:
        frappe.logger().error(f"[Tag Sync] No Sales Order linked to {doc.name}. Stopping.")
        return

    try:
        # 1. Get the Sales Order document itself
        # We need the full doc to use the .get_tags() method
        so = frappe.get_doc("Sales Order", doc.sales_order)
        
        # 2. Get the list of tags from the Sales Order
        so_tags = so.get_tags()

        if not so_tags:
            frappe.logger().error(f"[Tag Sync] No tags found on Sales Order {so.name}. Nothing to copy.")
            return

        frappe.logger().error(f"[Tag Sync] Found tags on {so.name}: {so_tags}")

        # 3. Add each tag to the new Work Order ('doc')
        for tag in so_tags:
            # Using the 'doc.add_tag()' method as you suggested.
            # This creates the "Tag Link" record automatically.
            doc.add_tag(tag)
            frappe.logger().error(f"[Tag Sync] Applied tag '{tag}' to {doc.name}")
        
        frappe.logger().error(f"[Tag Sync] SUCCESS: Finished copying tags to {doc.name}")

    except Exception as e:
        # Log any other errors
        frappe.log_error(f"Error in 'copy_tags_from_sales_order': {e}", "Tag Sync Error")