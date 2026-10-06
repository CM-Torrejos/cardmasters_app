# Custom Gross Profit v3

Select **Group By: Invoice** and enable **Show Manufacturing Cost Breakdown**.
Expand an invoice item to see its manufacture entries, then expand an entry to
see consumed materials, scrap credits and additional costs. Other grouping
options retain v2's summary layout.

Entries are matched through the invoice item's Sales Order item, its submitted
Work Orders and their submitted manufacture Stock Entries. The finished item
code must match. All matching production entries posted through **To Date** are
included, even when production occurred before **From Date**. Parent document
permissions apply; users need read access to Work Orders and Stock Entries to
see the breakdown.

The allocation factor is the net invoiced stock quantity divided by the total
matching produced stock quantity. It scales each entry's materials and costs
to that sale. Negative quantities reverse the allocation for returns. This is
a proportional production breakdown, not delivery batch tracing.

For entries with multiple finished goods, materials and scrap are apportioned
by the selected item's share of finished goods' basic value. If all basic
values are zero, their stock quantity share is used. Additional costs use the
amount recorded on the selected finished goods rows. Separate Material
Consumption for Manufacture entries supply materials when the manufacture
entry contains none.

**Manufacturing Allocation Adjustment** shows any difference between the
displayed components and the finished goods' recorded value, including manual
valuation changes or unavailable source components. **Valuation Difference**
shows the difference between the allocated manufacturing value and the
invoice item's Buying Amount.

Breakdown quantities use stock UOM and costs use company currency. Detail rows
use separate breakdown columns and do not contribute to the invoice totals or
gross profit totals. Production headers subtotal their own component children;
do not sum both levels together.

Accounting dimensions, including an enabled Branch dimension, register against
this report's own name and filter invoice item rows before allocation.
