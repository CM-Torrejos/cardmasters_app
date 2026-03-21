import frappe
from frappe.model.naming import make_autoname

def autoname(doc, method=None):
    """
    Custom naming for Employee: CM-[BranchAbbr][YY]-[Grade][Sequence]
    Sequence resets yearly but is shared across all Branches/Grades.
    """
    abbr = get_branch_abbr(doc.branch)
    year = get_joining_year(doc)
    
    # Generate the global sequence for the year
    # Result example: 'EMP-GLOBAL-26-0088'
    series_key = f"EMP-GLOBAL-{year}-.####"
    full_series = make_autoname(series_key)
    sequence = full_series.split('-')[-1]
    
    # Set the final name
    doc.name = f"CM-{abbr}{year}-{doc.grade or 'L0'}{sequence}"

def get_branch_abbr(branch_name):
    if not branch_name:
        return "UNK"
    return frappe.db.get_value("Branch", branch_name, "custom_abbreviation") or "UNK"

def get_joining_year(doc):
    if doc.date_of_joining:
        return frappe.utils.getdate(doc.date_of_joining).strftime('%y')
    return frappe.utils.nowdate()[:4][2:]