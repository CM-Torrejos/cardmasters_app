import json

import frappe
from frappe.desk.doctype.workspace.workspace import Workspace


class CustomWorkspace(Workspace):
    def build_links_table_from_card(self, config):
        # Core rebuilds each card using an explicit list of standard fields.
        # Restore our field on the newly appended rows, including duplicate targets.
        for card in config:
            super().build_links_table_from_card([card])
            links = json.loads(card.get("links") or "[]")
            if links:
                for row, source in zip(self.links[-len(links):], links):
                    row.custom_card_filters = (
                        source.get("custom_card_filters") if row.link_type == "DocType" else None
                    )
                    row.custom_card_show_count = (
                        source.get("custom_card_show_count", 0) if row.link_type == "DocType" else 0
                    )
                    row.custom_card_count_color = source.get("custom_card_count_color") or "Grey"

    def validate(self):
        super().validate()
        for row in self.links:
            if row.link_type != "DocType" or row.type != "Link":
                row.custom_card_filters = None
                row.custom_card_show_count = 0
                continue
            if not row.get("custom_card_filters"):
                continue
            try:
                filters = json.loads(row.custom_card_filters)
                if not isinstance(filters, list) or any(
                    not isinstance(f, list) or len(f) < 4
                    or not all(isinstance(v, str) for v in f[:3]) for f in filters
                ):
                    raise ValueError
            except (ValueError, TypeError):
                frappe.throw(frappe._("Row {0}: invalid card link filters.").format(row.idx))
