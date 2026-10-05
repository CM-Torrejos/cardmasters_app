"""Gross profit with an auditable, proportional manufacturing cost tree.

Manufacturing allocations explain the selling item's valuation; they never
change the gross profit calculated by v2. Quantities are in stock UOM.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt

from cardmasters_app.cardmasters_app.report.custom_gross_profit_v2 import custom_gross_profit_v2 as v2


def execute(filters=None):
	filters = frappe._dict(filters or {})
	filters.setdefault("group_by", "Invoice")
	generator = GrossProfitGenerator(filters)
	columns, data = v2.build_report(filters, generator)
	if filters.group_by != "Invoice":
		return columns, data

	columns.extend(get_breakdown_columns())
	data = add_cost_tree(data, generator, cint(filters.get("show_cost_breakdown", 1)))
	message = _(
		"Expand a sold item to see its manufacturing costs. Breakdown Cost is in company currency; "
		"quantities are in stock UOM. Costs are allocated proportionally across linked production "
		"entries posted through To Date using the net invoiced quantity, not traced to a delivery batch. "
		"Material allocation for multiple finished goods uses their basic value share "
		"(quantity share when all basic values are zero). Valuation Difference reconciles the "
		"manufacturing allocation to Buying Amount. Breakdown rows do not add to gross profit totals. "
		"Only Work Orders and Stock Entries you can read are included."
	)
	return columns, data, message


def get_breakdown_columns():
	return [
		{"fieldname": "row_type", "label": _("Row Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "cost_description", "label": _("Cost Description"), "fieldtype": "Data", "width": 240},
		{
			"fieldname": "work_order",
			"label": _("Work Order"),
			"fieldtype": "Link",
			"options": "Work Order",
			"width": 150,
		},
		{
			"fieldname": "source_qty",
			"label": _("Production / Source Qty"),
			"fieldtype": "Float",
			"width": 150,
		},
		{"fieldname": "allocated_qty", "label": _("Allocated Qty"), "fieldtype": "Float", "width": 120},
		{
			"fieldname": "stock_uom",
			"label": _("Stock UOM"),
			"fieldtype": "Link",
			"options": "UOM",
			"width": 100,
		},
		{
			"fieldname": "component_rate",
			"label": _("Source Unit Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 130,
		},
		{
			"fieldname": "breakdown_cost",
			"label": _("Breakdown Cost"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
	]


class GrossProfitGenerator(v2.GrossProfitGenerator):
	def get_manufacture_entries(self):
		"""Load all readable production entries, matched by SO row and finished item."""
		self.production = defaultdict(list)
		self.manufacture_entries = {}
		so_details = sorted({row.so_detail for row in self.si_list if row.so_detail})
		if (
			not so_details
			or not frappe.has_permission("Work Order", "read")
			or not frappe.has_permission("Stock Entry", "read")
		):
			return

		work_orders = frappe.get_list(
			"Work Order",
			filters={"sales_order_item": ["in", so_details], "docstatus": 1, "company": self.filters.company},
			fields=["name", "sales_order_item"],
			limit_page_length=0,
		)
		work_orders = {wo.name: wo.sales_order_item for wo in work_orders}
		if not work_orders:
			return

		entries = frappe.get_list(
			"Stock Entry",
			filters={
				"work_order": ["in", list(work_orders)],
				"docstatus": 1,
				"company": self.filters.company,
				"purpose": ["in", ["Manufacture", "Material Consumption for Manufacture"]],
				"posting_date": ["<=", self.filters.to_date],
			},
			fields=["name", "work_order", "posting_date", "posting_time", "purpose"],
			order_by="posting_date asc, posting_time asc, name asc",
			limit_page_length=0,
		)
		if not entries:
			return
		# Parent permissions have been checked by get_list; never read arbitrary child rows.
		items = frappe.get_all(
			"Stock Entry Detail",
			filters={"parent": ["in", [entry.name for entry in entries]], "parenttype": "Stock Entry"},
			fields=[
				"name",
				"parent",
				"idx",
				"item_code",
				"item_name",
				"stock_uom",
				"transfer_qty",
				"basic_amount",
				"additional_cost",
				"amount",
				"s_warehouse",
				"t_warehouse",
				"is_finished_item",
				"is_scrap_item",
			],
			order_by="parent asc, idx asc",
			limit_page_length=0,
		)
		items_by_entry = defaultdict(list)
		for item in items:
			items_by_entry[item.parent].append(item)
		consumption_by_wo = defaultdict(list)
		for entry in entries:
			if entry.purpose == "Material Consumption for Manufacture":
				consumption_by_wo[entry.work_order].extend(items_by_entry[entry.name])

		for entry in entries:
			if entry.purpose != "Manufacture":
				continue
			entry.production_items = items_by_entry[entry.name]
			entry.consumption_items = consumption_by_wo[entry.work_order]
			finished_codes = {
				item.item_code
				for item in entry.production_items
				if item.is_finished_item and item.t_warehouse
			}
			for item_code in finished_codes:
				if (
					sum(
						flt(item.transfer_qty)
						for item in entry.production_items
						if item.is_finished_item and item.item_code == item_code
					)
					> 0
				):
					self.production[(work_orders[entry.work_order], item_code)].append(entry)

		for row in self.si_list:
			linked = self.production.get((row.so_detail, row.item_code), [])
			row.manufacture_entry = linked[-1].name if linked else None


def add_cost_tree(data, generator, show_breakdown=True):
	"""Keep base rows/totals intact; use unique IDs even for duplicate item codes."""
	result = []
	ancestors = {}
	for index, (row, source) in enumerate(zip(data, generator.si_list, strict=False)):
		indent = int(source.indent or 0)
		row.report_row_id = f"report-{index}"
		row.parent_row_id = ancestors.get(indent - 1)
		row.row_type = "invoice" if indent == 0 else "item"
		ancestors[indent] = row.report_row_id
		result.append(row)
		entries = generator.production.get((source.so_detail, source.item_code), [])
		if not show_breakdown or indent != 1 or source.cost_accuracy != "Costed" or not entries:
			continue
		result.extend(
			get_cost_breakdown(source, entries, row.report_row_id, row.currency, generator.currency_precision)
		)
	# v2 appends its own total after the source rows; never total the detail tree.
	result.extend(data[len(generator.si_list) :])
	return result


def get_cost_breakdown(source, entries, parent_id, currency, precision=3):
	produced_qty = sum(
		flt(item.transfer_qty)
		for entry in entries
		for item in entry.production_items
		if item.is_finished_item and item.t_warehouse and item.item_code == source.item_code
	)
	if produced_qty <= 0:
		return []
	factor = flt(source.qty) / produced_qty
	rows = []
	production_cost = 0
	for index, entry in enumerate(entries):
		finished = [item for item in entry.production_items if item.is_finished_item and item.t_warehouse]
		target = [item for item in finished if item.item_code == source.item_code]
		qty = sum(flt(item.transfer_qty) for item in target)
		if qty <= 0:
			continue
		total_basic = sum(flt(item.basic_amount) for item in finished)
		share = (
			sum(flt(item.basic_amount) for item in target) / total_basic
			if total_basic
			else qty / sum(flt(item.transfer_qty) for item in finished)
		)
		entry_cost = flt(sum(flt(item.amount) for item in target) * factor, precision)
		production_cost += entry_cost
		entry_id = f"{parent_id}-production-{index}"
		rows.append(
			frappe._dict(
				report_row_id=entry_id,
				parent_row_id=parent_id,
				indent=2,
				sales_invoice=_("Manufacture"),
				row_type="manufacture",
				manufacture_entry=entry.name,
				work_order=entry.work_order,
				posting_date=entry.posting_date,
				source_qty=qty,
				allocated_qty=qty * factor,
				stock_uom=target[0].stock_uom,
				component_rate=sum(flt(item.amount) for item in target) / qty,
				breakdown_cost=entry_cost,
				currency=currency,
			)
		)
		components = []
		materials = [item for item in entry.production_items if item.s_warehouse and not item.t_warehouse]
		if not materials:
			materials = [
				item for item in entry.consumption_items if item.s_warehouse and not item.t_warehouse
			]
		for item in materials:
			components.append(component_row(item, "material", share * factor, precision))
		for item in entry.production_items:
			if item.is_scrap_item and item.t_warehouse and not item.s_warehouse:
				components.append(component_row(item, "scrap", -share * factor, precision))
		additional = sum(flt(item.additional_cost) for item in target) * factor
		if additional:
			components.append(
				frappe._dict(
					sales_invoice=_("Additional Costs"),
					row_type="additional_cost",
					cost_description=_("Operating and other costs allocated to the finished item"),
					breakdown_cost=flt(additional, precision),
				)
			)
		adjustment = flt(entry_cost - sum(item.breakdown_cost for item in components), precision)
		if adjustment:
			components.append(
				frappe._dict(
					sales_invoice=_("Manufacturing Allocation Adjustment"),
					row_type="manufacturing_adjustment",
					cost_description=_(
						"Finished item value not explained by the displayed materials, scrap and additional costs"
					),
					breakdown_cost=adjustment,
				)
			)
		for component_index, component in enumerate(components):
			component.update(
				report_row_id=f"{entry_id}-component-{component_index}",
				parent_row_id=entry_id,
				indent=3,
				currency=currency,
				work_order=entry.work_order,
			)
			component.setdefault("manufacture_entry", entry.name)
			rows.append(component)

	difference = flt(flt(source.buying_amount) - production_cost, precision)
	if difference:
		rows.append(
			frappe._dict(
				report_row_id=f"{parent_id}-valuation-difference",
				parent_row_id=parent_id,
				indent=2,
				sales_invoice=_("Valuation Difference"),
				row_type="valuation_difference",
				cost_description=_("Buying Amount minus the proportional manufacturing cost"),
				breakdown_cost=difference,
				currency=currency,
			)
		)
	return rows


def component_row(item, row_type, allocation, precision):
	qty = flt(item.transfer_qty)
	return frappe._dict(
		sales_invoice=item.item_code,
		item_name=item.item_name,
		row_type=row_type,
		cost_description=item.item_name,
		warehouse=item.s_warehouse or item.t_warehouse,
		manufacture_entry=item.parent,
		source_qty=qty,
		allocated_qty=qty * allocation,
		stock_uom=item.stock_uom,
		component_rate=flt(item.basic_amount) / qty if qty else 0,
		breakdown_cost=flt(flt(item.basic_amount) * allocation, precision),
	)
