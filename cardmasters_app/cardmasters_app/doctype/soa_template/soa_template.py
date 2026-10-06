import frappe
from frappe.model.document import Document

from cardmasters_app.cardmasters_app.services.soa_templates import validate_template_document


class SOATemplate(Document):
    def validate(self):
        validate_template_document(self)
        if self.is_default:
            other = frappe.db.get_value("SOA Template", {
                "report_type": self.report_type, "is_default": 1, "name": ["!=", self.name]
            }, "name")
            if other:
                frappe.throw(frappe._("{0} is already the default for this report. Uncheck its default flag first.").format(other))
