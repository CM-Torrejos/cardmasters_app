from erpnext.manufacturing.doctype.job_card.job_card import JobCard as BaseJobCard

class JobCard(BaseJobCard):
    def has_overlap(self, production_capacity, time_logs):
        # always return False → never treat logs as overlapping
        return False