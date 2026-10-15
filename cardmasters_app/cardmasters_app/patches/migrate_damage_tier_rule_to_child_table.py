import frappe

def execute():
    """
    1. Ensures child table columns exist on `tabDamage Tier Rule`.
    2. Links existing standalone records to the 'Damage Point Settings' Single DocType.
    """
    table_name = "Damage Tier Rule"
    db_table = f"tab{table_name}"

    if not frappe.db.table_exists(table_name):
        return

    # 1. Ensure the 3 child table columns exist in the database
    child_columns = [
        ("parent", "varchar(140)"),
        ("parentfield", "varchar(140)"),
        ("parenttype", "varchar(140)")
    ]

    for col_name, col_type in child_columns:
        if not frappe.db.has_column(table_name, col_name):
            frappe.db.sql(
                f"ALTER TABLE `{db_table}` ADD COLUMN `{col_name}` {col_type} DEFAULT NULL"
            )

    # 2. Reload metadata
    frappe.reload_doctype(table_name, force=True)
    frappe.reload_doctype("Damage Point Settings", force=True)

    # 3. Fetch records created prior to becoming a child table
    standalone_records = frappe.db.sql(
        f"""
        SELECT name
        FROM `{db_table}`
        WHERE parent IS NULL OR parent = ''
        ORDER BY creation ASC
        """,
        as_dict=True,
    )

    if not standalone_records:
        return

    # 4. Get the starting index
    current_max_idx = frappe.db.sql(
        f"""
        SELECT COALESCE(MAX(idx), 0)
        FROM `{db_table}`
        WHERE parent = 'Damage Point Settings'
          AND parentfield = 'damage_tier_rules'
        """
    )[0][0]

    # 5. Attach orphan records to 'Damage Point Settings'
    for idx, row in enumerate(standalone_records, start=current_max_idx + 1):
        frappe.db.sql(
            f"""
            UPDATE `{db_table}`
            SET parent = 'Damage Point Settings',
                parenttype = 'Damage Point Settings',
                parentfield = 'damage_tier_rules',
                idx = %s
            WHERE name = %s
            """,
            (idx, row.name),
        )

    # 6. Clear cache for the Single DocType
    frappe.clear_cache(doctype="Damage Point Settings")