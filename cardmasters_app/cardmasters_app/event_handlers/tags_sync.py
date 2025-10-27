import frappe
from frappe.desk.doctype.tag.tag import check_user_tags

frappe.utils.logger.set_log_level("INFO")
logger = frappe.logger("automated_tagging", allow_site=True, with_more_info=False)

def set_work_order_tags_from_sales_order(doc, method):
    """
    Hook: Work Order - after_insert
    Action: Pulls tags from the linked Sales Order when a new Work Order is created.
    'doc' is the new Work Order document.
    """
    
    logger.info(f"HOOK 'after_insert' running for WO: {doc.name}")

    if not doc.sales_order:
        logger.error(f"No Sales Order linked to {doc.name}. Stopping.")
        return

    try:
        # 1. Get the Sales Order document itself
        # We need the full doc to use the .get_tags() method
        so = frappe.get_doc("Sales Order", doc.sales_order)
        
        # 2. Get the list of tags from the Sales Order
        so_tags = so.get_tags()

        if not so_tags:
            logger.info(f"No tags found on Sales Order {so.name}. Nothing to copy.")
            return

        logger.info(f"Found tags on {so.name}: {so_tags}")

        # 3. Add each tag to the new Work Order ('doc')
        for tag in so_tags:
            doc.add_tag(tag)
            logger.info(f"Applied tag '{tag}' to {doc.name}")
        
        logger.info(f"SUCCESS: Finished copying tags to {doc.name}")

    except Exception as e:
        # Log any other errors
        frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())

def sync_new_sales_order_tags_to_work_orders(doc, method):
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
    
    logger.info(f"HOOK 'after_insert' running for Tag Link.")

    sales_order_name = doc.document_name
    new_tag = doc.tag

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
            logger.info(f"No active (Draft/Submitted) Work Orders found for {sales_order_name}.")
            return

        logger.info(f"Found {len(linked_wos)} active WOs to update.")

        # 3. Loop through each found Work Order and add the new tag
        for wo in linked_wos:
            try:
                wo_doc = frappe.get_doc("Work Order", wo.name)
                
                # add_tag is smart and will not add a duplicate
                wo_doc.add_tag(new_tag)
                
                logger.info(f"Applied tag '{new_tag}' to WO: {wo_doc.name}")

            except Exception as e:
                frappe.log_error(f"Error applying tag to WO {wo.name}: {e}", "Automated Tagging Error")

        logger.info(f"SUCCESS: Finished syncing tag '{new_tag}' to WOs.")

    except Exception as e:
        frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())

@frappe.whitelist()
def sync_work_order_tags_on_sales_order_tag_removal(tag, dt, dn):
    """
    Hook: override_whitelisted_methods
    Action: Overrides the standard 'remove_tag' function.
        1. Runs our custom logic to remove tags from linked WOs.
        2. Runs the original 'remove_tag' logic to delete the Tag Link.
    
    'tag' is the tag name (e.g., "MyTag")
    'dt' is the doctype (e.g., "Sales Order")
    'dn' is the doc name (e.g., "SO-00001")
    """
    
    logger.info(f"OVERRIDE 'remove_tag' fired for: {dt} '{dn}' (Tag: {tag})")

    # --- 1. Our Custom Logic (Run FIRST) ---
    if dt == "Sales Order":
        sales_order_name = dn
        removed_tag = tag
        
        logger.info(f"Tag '{removed_tag}' removed from SO: {sales_order_name}. Finding WOs...")
        
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
                logger.info(f"No active WOs found for {sales_order_name}.")
            else:
                logger.info(f"Found {len(linked_wos)} active WOs to check for tag removal.")
                
                for wo in linked_wos:
                    try:
                        wo_doc = frappe.get_doc("Work Order", wo.name)
                        wo_doc.remove_tag(removed_tag)
                        wo_doc.save(ignore_permissions=True) # Save the WO
                        logger.info(f"Removed tag '{removed_tag}' from WO: {wo_doc.name}")
                    except Exception as e:
                        frappe.log_error(f"Error removing tag from WO {wo.name}: {e}", "Tag Sync Error")
            
            logger.info(f"SUCCESS: Finished syncing removed tag '{removed_tag}'.")

        except Exception as e:
            frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())
    
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
        so_doc = frappe.get_doc(dt, dn)
        current_tags = so_doc.get_tags()
        if tag in current_tags:
            current_tags.remove(tag)
            
        new_tag_string = ",".join(current_tags)
        if new_tag_string and not new_tag_string.startswith(","):
            new_tag_string = "," + new_tag_string
             
        # Update the SO's _user_tags field
        frappe.db.set_value(dt, dn, "_user_tags", new_tag_string, update_modified=False)

        logger.info(f"Original 'remove_tag' logic executed for {dn}.")

    except Exception as e:
        frappe.log_error(f"Error in original remove_tag logic: {e}", "Tag Sync Error")
        raise e

def automated_sales_order_tagging(doc, method):
    """
    Hook: Sales Order - after_insert, on_update
    Action: Checks conditions and automatically adds/removes 'BLUE ORDER' tag.
    'doc' is the Sales Order document that was just saved.
    """
    
    # We don't want this to run on cancelled (docstatus=2) documents
    if doc.docstatus == 2:
        return

    TAG_TO_APPLY = "BLUE ORDER"
    should_have_tag = False
    
    logger.info(f"HOOK '{method}' running for SO: {doc.name}")

    try:
        # --- 1. Check Conditions ---
        
        # Condition 1: Customer is Class A
        if doc.customer:
            customer_class = frappe.db.get_value("Customer", doc.customer, "custom_class")
            if customer_class == "A":
                should_have_tag = True
                logger.info(f"Condition 1 MET: Customer is Class A.")

        # Condition 2: Sponsored checkbox is ticked
        if not should_have_tag and getattr(doc, "custom_sponsored", 0): # doc.custom_sponsored == 1
            should_have_tag = True
            logger.info(f"Condition 2 MET: Sponsored is ticked.")

        # Condition 3: Grand total is >= 80,000
        if not should_have_tag and doc.grand_total >= 80000:
            should_have_tag = True
            logger.info(f"Condition 3 MET: Grand Total is >= 80000.")

        # --- 2. Apply or Remove Tag ---
        
        # Get the list of tags currently on the doc
        current_tags = doc.get_tags()
        tag_is_present = TAG_TO_APPLY in current_tags

        if should_have_tag and not tag_is_present:
            # ADD THE TAG
            doc.add_tag(TAG_TO_APPLY)
            logger.info(f"ADDED tag '{TAG_TO_APPLY}' to {doc.name}")
            
        elif not should_have_tag and tag_is_present:
            # REMOVE THE TAG
            doc.remove_tag(TAG_TO_APPLY)
            logger.info(f"ACTION: REMOVED tag '{TAG_TO_APPLY}' from {doc.name}")
            
        else:
            logger.info(f"ACTION: No change needed.")

    except Exception as e:
        frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())