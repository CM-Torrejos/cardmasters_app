import frappe

def calculate_time_difference(doc, method):
    """
    Hooked into before_save of Artist Sheet.
    When workflow_state == 'Client Approved',
    set time_difference = expected_total_time - total_time_in_minutes.
    Otherwise clear it.
    """
    # ensure we have numeric values
    expected = doc.expected_total_time or 0
    actual   = doc.total_time_in_minutes or 0

    if doc.workflow_state == "Client Approved":
        # assign difference
        doc.time_difference = expected - actual
    else:
        # reset (optional—drop this line if you want to preserve old values)
        doc.time_difference = None