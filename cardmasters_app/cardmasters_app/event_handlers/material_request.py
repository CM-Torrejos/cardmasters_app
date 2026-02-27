import frappe
from frappe import _

def validate_material_request(doc, _method):
    # look for any RMGEN lines
    has_rmgen = any(d.item_code == "RMGEN" for d in doc.items)

    if doc.material_request_type == "Purchase":
        if has_rmgen:
            # check the custom checkbox
            doc.custom_has_unregistered_items = 1

    elif doc.material_request_type == "Transfer":
        if has_rmgen:
            # block transfers of unregistered items
            frappe.throw(
                _("Unregistered items have no stock and therefore cannot be transferred. Create a purchase request instead!")
            )


# def stock_entry_before_insert(doc, method):
# 	"""
# 	Hook: before_insert on Stock Entry.
# 	If this Stock Entry was generated from a Material Request, fetch that MR,
# 	take its first item row’s `sales_order` value, and populate doc.custom_sales_order.
# 	"""
# 	# Only proceed if this Stock Entry is linked to a Material Request
# 	mr_name = doc.get("material_request")
# 	if not mr_name:
# 		return

# 	try:
# 		mr = frappe.get_doc("Material Request", mr_name)
# 	except frappe.DoesNotExistError:
# 		# If the MR was deleted or invalid, just skip
# 		return

# 	if mr.items:
# 		first_item = mr.items[0]
# 		so_name = first_item.get("sales_order")
# 		if so_name:
# 			# Assume `custom_sales_order` is your custom Data/Link field on Stock Entry
# 			doc.custom_sales_order = so_name


# # Helper function to identify parent group
# # You must have the is_descendant_of function defined in the same file
# # or imported.
# def is_descendant_of(child_item_group, ancestor_item_group):
#     if not child_item_group or not ancestor_item_group:
#         return False
#     current_group = child_item_group
#     while current_group:
#         if current_group == ancestor_item_group:
#             # We will consider the group itself a descendant for this check
#             return True
#         parent_group = frappe.db.get_value("Item Group", current_group, "parent_item_group")
#         if parent_group == ancestor_item_group:
#             return True
#         current_group = parent_group
#     return False

# # Your validation function, corrected
# def validate_request(doc, method):
#     if doc.material_request_type == 'Purchase':
#         # Check for a sales_order on the main document
#         for item in doc.items:
#             # 1. Get the item_group for the item in the current row
#             item_group = frappe.db.get_value("Item", item.item_code, "item_group")

#             # 2. Check if the item_group IS a descendant of 'PRODUCTS'
#             # 3. Also check if the item_code matches 'RMGEN'
#             if is_descendant_of(item_group, 'PRODUCTS'):
#                 # 4. Throw an error with the correct row index (item.idx)
#                 frappe.throw(_("Row {idx}: Item {item_code} is a finished good and cannot be purchase requested without a Sales Order.").format(idx=item.idx, item_code=item.item_code))

# 			if item.item_code == "RMGEN" and 