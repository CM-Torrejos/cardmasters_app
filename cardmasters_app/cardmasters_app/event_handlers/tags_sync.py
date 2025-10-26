import frappe
from frappe.desk.doctype.tag.tag import check_user_tags

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

"""
Function 3: Works via 'override_whitelisted_methods'
Replaces the 'remove_tag' function to sync deletions.
"""
@frappe.whitelist() # This is CRITICAL.
def custom_remove_tag_and_sync(tag, dt, dn): # <-- THE FIX IS HERE
    """
    Hook: override_whitelisted_methods
    Action: Overrides the standard 'remove_tag' function.
            1. Runs our custom logic to remove tags from linked WOs.
            2. Runs the original 'remove_tag' logic to delete the Tag Link.
    
    'tag' is the tag name (e.g., "MyTag")
    'dt' is the doctype (e.g., "Sales Order")
    'dn' is the doc name (e.g., "SO-00001")
    """
    
    # We are logging the correct variables now
    frappe.logger().error(
        f"[Tag Sync] OVERRIDE 'remove_tag' fired for: {dt} '{dn}' (Tag: {tag})"
    )

    # --- 1. Our Custom Logic (Run FIRST) ---
    if dt == "Sales Order":  # <-- Use 'dt'
        sales_order_name = dn  # <-- Use 'dn'
        removed_tag = tag
        
        frappe.logger().error(f"[Tag Sync] Tag '{removed_tag}' removed from SO: {sales_order_name}. Finding WOs...")
        
        try:
            # Find all 'Draft' (0) and 'Submitted' (1) WOs
            linked_wos = frappe.get_all("Work Order",
                filters={
                    "sales_order": sales_order_name,
                    "docstatus": ["in", [0, 1]],
                    "status": ["not in", ["Completed", "Cancelled"]]
                },
                fields=["name"]
            )

            if not linked_wos:
                frappe.logger().error(f"[Tag Sync] No active WOs found for {sales_order_name}.")
            else:
                frappe.logger().error(f"[Tag Sync] Found {len(linked_wos)} active WOs to check for tag removal.")
                
                for wo in linked_wos:
                    try:
                        wo_doc = frappe.get_doc("Work Order", wo.name)
                        wo_doc.remove_tag(removed_tag)
                        wo_doc.save(ignore_permissions=True) # Save the WO
                        frappe.logger().error(f"[Tag Sync] Removed tag '{removed_tag}' from WO: {wo_doc.name}")
                    except Exception as e:
                        frappe.log_error(f"Error removing tag from WO {wo.name}: {e}", "Tag Sync Error")
            
            frappe.logger().error(f"[Tag Sync] SUCCESS: Finished syncing removed tag '{removed_tag}'.")

        except Exception as e:
            frappe.log_error(f"Error in 'sync_removed_tag_from_sales_order': {e}", "Tag Sync Error")
    
    # --- 2. Original Function Logic (Run LAST) ---
    # This logic is copied from tag.py to make the tag
    # actually delete from the Sales Order.
    try:
        check_user_tags(tag) # Perform original permission check

        # This is the line from update_tags()
        frappe.db.delete(
            "Tag Link",
            {
                "document_type": dt,  # <-- Use 'dt'
                "document_name": dn,  # <-- Use 'dn'
                "tag": tag,
            },
        )

        # We also have to update the `_user_tags` column in the Sales Order
        so_doc = frappe.get_doc(dt, dn) # <-- Use 'dt', 'dn'
        current_tags = so_doc.get_tags()
        if tag in current_tags:
            current_tags.remove(tag)
            
        new_tag_string = ",".join(current_tags)
        if new_tag_string:
             new_tag_string = "," + new_tag_string
             
        # Update the SO's _user_tags field
        frappe.db.set_value(dt, dn, "_user_tags", new_tag_string, update_modified=False)

        frappe.logger().error(f"[Tag Sync] Original 'remove_tag' logic executed for {dn}.")

    except Exception as e:
        frappe.log_error(f"Error in original remove_tag logic: {e}", "Tag Sync Error")
        raise e