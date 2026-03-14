import frappe
from frappe import _

def execute(filters=None):
    columns = get_columns()
    data = []

    # 1. Fetch Sales Orders (Excluding Concluded)
    so_filters = {
        "docstatus": 1,
        "workflow_state": ["!=", "Production Concluded"]
    }
    if filters.get("from_date") and filters.get("to_date"):
        so_filters["transaction_date"] = ["between", [filters.from_date, filters.to_date]]
    if filters.get("workflow_state"):
        so_filters["workflow_state"] = filters.workflow_state

    sales_orders = frappe.get_all("Sales Order", 
        filters=so_filters,
        fields=["name", "customer", "delivery_date", "workflow_state"],
        order_by="delivery_date desc"
    )

    for so in sales_orders:
        so_rows = []
        so_total_qty_sum = 0
        so_total_produced_sum = 0
        so_has_bypass = 0
        
        eligible_item_count = 0
        fully_planned_item_count = 0

        # 2. Fetch Items (L2)
        items = frappe.get_all("Sales Order Item",
            filters={"parent": so.name},
            fields=["item_code", "item_name", "qty", "name", "bom_no"]
        )

        for item in items:
            if not item.bom_no: continue
            
            eligible_item_count += 1
            
            # 3. Fetch Work Orders (L3)
            wos = frappe.get_all("Work Order",
                filters={
                    "sales_order": so.name, 
                    "production_item": item.item_code, 
                    "sales_order_item": item.name,
                    "docstatus": ["!=", 2]
                },
                fields=["name", "status", "produced_qty", "qty", "custom_bypass"]
            )

            l3_rows = []
            item_produced_acc = 0
            item_planned_acc = 0
            
            for wo in wos:
                wo_qty = wo.qty or 0
                item_planned_acc += wo_qty 
                wo_produced = wo_qty if wo.custom_bypass else (wo.produced_qty or 0)
                item_produced_acc += wo_produced
                
                if wo.custom_bypass:
                    so_has_bypass = 1

                l3_rows.append({
                    "label_name": wo.name,
                    "wo_status": wo.status,
                    "produced_qty": wo.produced_qty,
                    "qty": wo_qty,
                    "completion_rate": f"{int(min((wo_produced / wo_qty * 100), 100)) if wo_qty > 0 else 0}%",
                    "is_bypass": wo.custom_bypass,
                    "indent": 2
                })

            if item_planned_acc >= item.qty:
                fully_planned_item_count += 1

            planning_status = "ok"
            if not wos:
                planning_status = "orphan"
            elif item_planned_acc < item.qty:
                planning_status = "shortfall"

            l2_perc = min((item_produced_acc / item.qty * 100), 100) if item.qty > 0 else 0
            so_total_qty_sum += item.qty
            so_total_produced_sum += min(item_produced_acc, item.qty)

            so_rows.append({
                "label_name": f"{item.item_code}: {item.item_name}",
                "qty": f"{int(item_planned_acc)} / {int(item.qty)}", 
                "produced_qty": item_produced_acc,
                "completion_rate": f"{int(l2_perc)}%",
                "is_bypass": 1 if any(wo.get('is_bypass') for wo in l3_rows) else 0,
                "planning_status": planning_status, 
                "indent": 1
            })
            so_rows.extend(l3_rows)

        so_perc = min((so_total_produced_sum / so_total_qty_sum * 100), 100) if so_total_qty_sum > 0 else 0
        incomplete_coverage = 1 if fully_planned_item_count != eligible_item_count else 0

        data.append({
            "label_name": f"{so.name} - {so.customer}",
            "date": so.delivery_date,
            "workflow_state": so.workflow_state,
            "completion_rate": f"{int(so_perc)}%",
            "qty": f"{fully_planned_item_count} / {eligible_item_count}", 
            "is_bypass": so_has_bypass,
            "is_orphan_so": 1 if eligible_item_count == 0 else 0,
            "incomplete_coverage": incomplete_coverage,
            "indent": 0
        })
        data.extend(so_rows)

    return columns, data

def get_columns():
    return [
        {"label": _("Reference (SO / Item / WO)"), "fieldname": "label_name", "fieldtype": "Data", "width": 400},
        {"label": _("Target Date"), "fieldname": "date", "fieldtype": "Date", "width": 110},
        {"label": _("Stage"), "fieldname": "workflow_state", "fieldtype": "Data", "width": 160},
        {"label": _("Completion"), "fieldname": "completion_rate", "fieldtype": "Data", "width": 110},
        {"label": _("Coverage (L0) / Plan (L1)"), "fieldname": "qty", "fieldtype": "Data", "width": 150}, 
        {"label": _("WO Status"), "fieldname": "wo_status", "fieldtype": "Data", "width": 130},
        {"label": _("Produced"), "fieldname": "produced_qty", "fieldtype": "Float", "width": 100},
        {"label": _("Bypass"), "fieldname": "is_bypass", "fieldtype": "Check", "width": 80},
    ]