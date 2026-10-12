"""Migrate the original Consumption draft directly to its final name."""

from cardmasters_app.cardmasters_app.patches.rename_print_pass_to_withdrawal import rename_draft


def execute():
	rename_draft((("Consumption", "Withdrawal"), ("Consumption Table", "Withdrawal Work Order")))
