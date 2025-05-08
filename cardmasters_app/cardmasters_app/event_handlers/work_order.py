import frappe

def inherit_remarks_particulars(doc, method=None):
    if doc.sales_order:
        sales_order = frappe.get_doc("Sales Order", doc.sales_order)
        
        # Fetch values from Sales Order
        doc.custom_remarks = sales_order.custom_remarks
        doc.custom_deadline = sales_order.delivery_date
        # Fetch the Sales Order Item description
        if doc.production_item:
            doc.custom_particulars = frappe.db.get_value(
                "Sales Order Item",
                {"parent": doc.sales_order, "item_code": doc.production_item},
                "custom_particulars"
            )

