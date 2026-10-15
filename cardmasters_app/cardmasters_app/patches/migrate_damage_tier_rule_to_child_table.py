import frappe

def execute():
    """
    Migrates standalone 'Damage Tier Rule' records to become child table rows
    under the Single DocType 'Damage Point Settings'.
    """
    # 1. Reload metadata to force schema sync (adds parent, parenttype, parentfield, idx)
    frappe.reload_doctype("Damage Tier Rule", force=True)
    frappe.reload_doctype("Damage Point Settings", force=True)

    if not frappe.db.table_exists("Damage Tier Rule"):
        return

    # 2. Retrieve records that were saved prior to becoming a child table
    standalone_records = frappe.db.sql(
        """
        SELECT name
        FROM `tabDamage Tier Rule`
        WHERE parent IS NULL OR parent = ''
        ORDER BY creation ASC
        """,
        as_dict=True,
    )

    if not standalone_records:
        return

    # 3. Determine base index in case records already exist under the parent
    current_max_idx = frappe.db.sql(
        """
        SELECT COALESCE(MAX(idx), 0)
        FROM `tabDamage Tier Rule`
        WHERE parent = 'Damage Point Settings'
          AND parentfield = 'damage_tier_rules'
        """
    )[0][0]

    # 4. Attach orphan records to 'Damage Point Settings'
    for idx, row in enumerate(standalone_records, start=current_max_idx + 1):
        frappe.db.sql(
            """
            UPDATE `tabDamage Tier Rule`
            SET parent = 'Damage Point Settings',
                parenttype = 'Damage Point Settings',
                parentfield = 'damage_tier_rules',
                idx = %s
            WHERE name = %s
            """,
            (idx, row.name),
        )

    # 5. Clear cached Single document data
    frappe.clear_cache(doctype="Damage Point Settings")