import frappe
from erpnext.manufacturing.doctype.work_order.work_order import WorkOrder
from frappe.utils import flt

class CustomWorkOrder(WorkOrder):
    def update_work_order_qty_in_so(self):
        if not self.sales_order and not self.sales_order_item:
            return

        total_bundle_qty = 1
        if self.product_bundle_item:
            total_bundle_qty = frappe.db.sql(
                """ select sum(qty) from
                `tabProduct Bundle Item` where parent = %s""",
                (frappe.db.escape(self.product_bundle_item)),
            )[0][0]

            if not total_bundle_qty:
                # product bundle is 0 (product bundle allows 0 qty for items)
                total_bundle_qty = 1

        cond = "product_bundle_item = %s" if self.product_bundle_item else "sales_order_item = %s"

        qty = frappe.db.sql(
            f""" select sum(qty) from
            `tabWork Order` where sales_order = %s and docstatus = 1 and status <> 'Closed' and {cond}
            """,
            (self.sales_order, (self.product_bundle_item or self.sales_order_item)),
            as_list=1,
        )

        work_order_qty = qty[0][0] if qty and qty[0][0] else 0
        frappe.db.set_value(
            "Sales Order Item",
            self.sales_order_item,
            "work_order_qty",
            flt(work_order_qty / total_bundle_qty, 2),
        )