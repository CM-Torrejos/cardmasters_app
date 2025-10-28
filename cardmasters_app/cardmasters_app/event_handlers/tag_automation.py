import frappe
from frappe.desk.doctype.tag.tag import check_user_tags

frappe.utils.logger.set_log_level("INFO")
logger = frappe.logger("automated_tagging", allow_site=True, with_more_info=False)

# ================================================================
# Configuration
# ================================================================
PROPAGATION_MAP = {
    "Sales Order": {
        "Work Order": {
            "link_field": "sales_order",
            "filters": {
                "docstatus": ["in", [0, 1]],
                "status": ["not in", ["Completed", "Cancelled"]],
            },
        },
        "Artist Card": {
            "link_field": "sales_order",
            "filters": {"docstatus": ["in", [0, 1]]},
        },
        "Job Card": {
            "link_field": "custom_sales_order",
            "filter": {
                "docstatus": ["in", [0, 1]],
                "status": ["not in", ["Completed", "Cancelled"]],
            }
        }
    },
}

# ================================================================
# Helper Functions
# ================================================================
def get_linked_docs(source_doctype: str, source_name: str):
    """
    Returns a dictionary of linked documents for the given source
    based on PROPAGATION_MAP configuration.
    """
    linked_docs_map = {}

    if source_doctype not in PROPAGATION_MAP:
        return linked_docs_map

    for target_doctype, config in PROPAGATION_MAP[source_doctype].items():
        link_field = config.get("link_field")
        filters = {link_field: source_name}
        filters.update(config.get("filters", {}))

        try:
            meta = frappe.get_meta(target_doctype)
            if not meta.has_field(link_field):
                logger.warning(f"Skipping {target_doctype}: Missing field '{link_field}'")
                continue
        except Exception as e:
            continue

        docs = frappe.get_all(target_doctype, filters=filters, fields=["name"])
        linked_docs_map[target_doctype] = docs

    return linked_docs_map

def apply_tag_to_linked_docs(source_doctype, source_name, tag):
    """
    Apply a tag to all linked documents defined in PROPAGATION_MAP.
    """

    linked_docs_map = get_linked_docs(source_doctype, source_name)

    for target_doctype, docs in linked_docs_map.items():
        if not docs:
            logger.info(f"No active {target_doctype} found linked to {source_doctype} {source_name}.")
            continue

        logger.info(f"Found {len(docs)} {target_doctype} docs linked to {source_doctype} {source_name}.")

        for linked in docs:
            try:
                target_doc = frappe.get_doc(target_doctype, linked.name)
                target_doc.add_tag(tag)
                logger.info(f"Added tag '{tag}' to {target_doctype} '{linked.name}'.")
            except Exception as e:
                frappe.log_error(f"Error adding tag to {target_doctype} {linked.name}: {e}", "Automated Tagging Error")

def remove_tag_from_linked_docs(source_doctype, source_name, tag):
    """
    Remove a tag from all linked documents defined in PROPAGATION_MAP.
    """
    linked_docs_map = get_linked_docs(source_doctype, source_name)

    for target_doctype, docs in linked_docs_map.items():
        if not docs:
            logger.info(f"No active {target_doctype} found linked to {source_doctype} {source_name}.")
            continue

        logger.info(f"Found {len(docs)} active {target_doctype} linked to {source_doctype} {source_name}.")

        for linked in docs:
            try:
                target_doc = frappe.get_doc(target_doctype, linked.name)
                target_doc.remove_tag(tag)
                target_doc.save(ignore_permissions=True)
                logger.info(f"Removed tag '{tag}' from {target_doctype} '{linked.name}'.")
            except Exception as e:
                frappe.log_error(f"Error removing tag from {target_doctype} {linked.name}: {e}", "Tag Sync Error")

# ================================================================
# Hook Functions
# ================================================================
def sync_linked_documents_on_master_document_tags_addition(doc, method):
    """
    Hook: Tag Link - after_insert
    Action: When a new tag is added to a source document, propagate it
            to all linked documents defined in PROPAGATION_MAP.
    """
    source_doctype = doc.document_type
    source_name = doc.document_name
    new_tag = doc.tag

    if source_doctype not in PROPAGATION_MAP:
        return

    logger.info(f"Running tag addition hook for {source_doctype} '{source_name}' (new tag: {new_tag})")

    try:
        apply_tag_to_linked_docs(source_doctype, source_name, new_tag)
        logger.info(f"Finished syncing tag '{new_tag}' from {source_doctype} '{source_name}'.")
    except Exception:
        frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())

@frappe.whitelist()
def sync_linked_documents_on_master_documemt_tags_removal(tag, dt, dn):
    """
    Overrides Frappe's remove_tag logic to also remove tags from linked documents
    before performing the actual Tag Link deletion.
    """
    logger.info(f"OVERRIDE 'remove_tag' fired for: {dt} '{dn}' (Tag: {tag})")

    # 1. Custom propagation removal
    if dt in PROPAGATION_MAP:
        try:
            remove_tag_from_linked_docs(dt, dn, tag)
            logger.info(f"Finished syncing removed tag '{tag}' from {dt} '{dn}'.")
        except Exception:
            frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())

    # 2. Original Frappe tag deletion logic
    try:
        check_user_tags(tag)

        frappe.db.delete(
            "Tag Link",
            {"document_type": dt, "document_name": dn, "tag": tag},
        )

        doc = frappe.get_doc(dt, dn)
        current_tags = doc.get_tags()

        if tag in current_tags:
            current_tags.remove(tag)

        new_tag_string = ",".join(current_tags)
        if new_tag_string and not new_tag_string.startswith(","):
            new_tag_string = "," + new_tag_string

        frappe.db.set_value(dt, dn, "_user_tags", new_tag_string, update_modified=False)
        logger.info(f"Original 'remove_tag' logic executed for {dt} '{dn}'.")

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

def sync_tags_from_master_on_creation(doc, method):
    """
    Hook: after_insert
    Generic tag propagation for any document creation.
    Automatically determines if this document is a target of propagation_map
    and copies tags from its linked master document.
    """

    logger.info(f"HOOK 'after_insert' running for {doc.doctype} '{doc.name}'")

    try:
        # Step 1: Find which master_doctype this document depends on
        for master_doctype, targets in PROPAGATION_MAP.items():
            if doc.doctype in targets:
                config = targets[doc.doctype]
                link_field = config.get("link_field")

                if not link_field:
                    logger.warning(f"No link_field specified for {doc.doctype} under {master_doctype}. Skipping.")
                    continue

                # Step 2: Get linked master document name
                master_name = getattr(doc, link_field, None)
                if not master_name:
                    logger.info(f"{doc.doctype} '{doc.name}' has no value for link field '{link_field}'. Skipping.")
                    continue

                # Step 3: Fetch master document and its tags
                master_doc = frappe.get_doc(master_doctype, master_name)
                master_tags = master_doc.get_tags()

                if not master_tags:
                    logger.info(f"No tags found on {master_doctype} '{master_doc.name}'. Nothing to sync.")
                    continue

                logger.info(
                    f"Found tags on {master_doctype} '{master_doc.name}': {master_tags}. "
                    f"Applying to {doc.doctype} '{doc.name}'."
                )

                # Step 4: Apply all tags to the new document
                for tag in master_tags:
                    doc.add_tag(tag)
                    logger.info(f"Applied tag '{tag}' to {doc.doctype} '{doc.name}'")

                logger.info(f"SUCCESS: Copied tags from {master_doctype} '{master_doc.name}' to {doc.doctype} '{doc.name}'")

        else:
            logger.debug(f"{doc.doctype} not found in any PROPAGATION_MAP target. Skipping tag sync.")

    except Exception:
        frappe.log_error(title="Automated Tagging Error", message=frappe.get_traceback())
