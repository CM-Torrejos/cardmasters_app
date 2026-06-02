import frappe


def clear_reversal_on_unreconcile_tool(doc, method=None):
    """
    Hook: Unreconcile Payment → on_submit
    Delegates to the payment_entry service to clear the reversal state.
    """
    from cardmasters_app.cardmasters_app.services.payment_entry import (
        clear_reversal_on_unreconcile_tool as _clear_reversal,
    )
    _clear_reversal(doc, method)


def clear_reversal_on_je_cancel(doc, method=None):
    """
    Hook: Journal Entry → on_cancel
    Delegates to the payment_entry service to clear the reversal link.
    """
    from cardmasters_app.cardmasters_app.services.payment_entry import (
        clear_reversal_on_je_cancel as _clear_je,
    )
    _clear_je(doc, method)
