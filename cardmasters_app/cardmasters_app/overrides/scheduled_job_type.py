from frappe.core.doctype.scheduled_job_type.scheduled_job_type import ScheduledJobType

NATIVE_SOA_JOB = "erpnext.accounts.doctype.process_statement_of_accounts.process_statement_of_accounts.send_auto_email"
CUSTOM_SOA_JOB = "cardmasters_app.cardmasters_app.services.soa_templates.send_auto_email"


class CustomScheduledJobType(ScheduledJobType):
    def execute(self):
        # Keep the native job, schedule, queue, logging and transaction handling.
        # Only its SOA callback needs the app's scoped template context.
        if self.method != NATIVE_SOA_JOB:
            return super().execute()
        original = self.method
        try:
            self.method = CUSTOM_SOA_JOB
            return super().execute()
        finally:
            self.method = original
