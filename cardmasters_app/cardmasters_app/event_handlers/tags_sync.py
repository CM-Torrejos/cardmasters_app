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

def sync_new_tag_to_work_orders(doc, method):
    """
    Hook: Tag Link - after_insert
    Action: When a new tag is linked to a document, check if it's a 
            Sales Order. If yes, find all active, linked Work Orders
            (Draft & Submitted) and apply the same tag to them.
    'doc' is the new 'Tag Link' document.
    """
    
    # 1. Check if the tag was added to a Sales Order.
    if doc.document_type != "Sales Order":
        return

    sales_order_name = doc.document_name
    new_tag = doc.tag

    frappe.logger().error(f"[Tag Sync] HOOK 'after_insert' running for Tag Link.")
    frappe.logger().error(f"[Tag Sync] New tag '{new_tag}' added to SO: {sales_order_name}")

    try:
        # 2. Find all 'Draft' (docstatus=0) and 'Submitted' (docstatus=1)
        #    Work Orders linked to this Sales Order that are not
        #    'Completed' or 'Cancelled'.
        linked_wos = frappe.get_all("Work Order",
            filters={
                "sales_order": sales_order_name,
                "docstatus": ["in", [0, 1]],  # <-- UPDATED: 0=Draft, 1=Submitted
                "status": ["not in", ["Completed", "Cancelled"]]
            },
            fields=["name"]
        )

        if not linked_wos:
            frappe.logger().error(f"[Tag Sync] No active (Draft/Submitted) Work Orders found for {sales_order_name}.")
            return

        frappe.logger().error(f"[Tag Sync] Found {len(linked_wos)} active WOs to update.")

        # 3. Loop through each found Work Order and add the new tag
        for wo in linked_wos:
            try:
                wo_doc = frappe.get_doc("Work Order", wo.name)
                
                # add_tag is smart and will not add a duplicate
                wo_doc.add_tag(new_tag)
                
                frappe.logger().error(f"[Tag Sync] Applied tag '{new_tag}' to WO: {wo_doc.name}")

            except Exception as e:
                frappe.log_error(f"Error applying tag to WO {wo.name}: {e}", "Tag Sync Error")

        frappe.logger().error(f"[Tag Sync] SUCCESS: Finished syncing tag '{new_tag}' to WOs.")

    except Exception as e:
        frappe.log_error(f"Error in 'sync_new_tag_to_work_orders': {e}", "Tag Sync Error")
