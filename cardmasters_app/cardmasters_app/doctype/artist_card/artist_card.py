# Copyright (c) 2025, Shan Torrejos and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_datetime, now_datetime

class ArtistCard(Document):
	def validate(self):
		# Automatically close active timer if the workflow state is transitioning
		if not self.is_new() and self.has_value_changed("workflow_state"):
			self.close_running_timer()

		# Always ensure total time is accurate
		self.calculate_total_time()

	def close_running_timer(self):
		if not self.timesheet:
			return

		last_row = self.timesheet[-1]

		# Only close if from_time is set and to_time is still empty (timer currently running)
		if last_row.from_time and not last_row.to_time:
			now = now_datetime()
			last_row.to_time = now

			# Calculate difference using datetime objects
			from_time = get_datetime(last_row.from_time)
			seconds = (now - from_time).total_seconds()
			last_row.time_in_minutes = round(seconds / 60.0, 2)

	def calculate_total_time(self):
		"""
		Sums 'time_in_minutes' across all timesheet rows.
		"""
		total = sum((row.time_in_minutes or 0) for row in (self.timesheet or []))
		self.finished_total_time = round(total, 2)

