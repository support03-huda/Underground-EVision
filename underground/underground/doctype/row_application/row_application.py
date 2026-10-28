# Copyright (c) 2026, huda and contributors
"""ROW Application — one record per authority on a site's route (the ROW Tracker).

Steps: application submitted → demand note → payment / SD / BG → permission received or
rejected. A rejected application is reapplied on the same record, not closed."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, cint, date_diff, getdate, today

from underground.underground.doctype.ug_site.ug_site import refresh_site
from underground.utils import get_setting


class ROWApplication(Document):
	def validate(self):
		self.validate_site()
		self.validate_duplicate()
		self.track_attempts()
		self.set_calculated()

	def on_update(self):
		refresh_site(self.ug_site)
		previous = self.get_doc_before_save()
		if previous and previous.ug_site != self.ug_site:
			refresh_site(previous.ug_site)

	def after_delete(self):
		refresh_site(self.ug_site)

	def validate_site(self):
		site = frappe.db.get_value("UG Site", self.ug_site, ["is_mobilization", "row_required"], as_dict=True)
		if site and site.is_mobilization:
			frappe.throw(_("{0} is a Mobilization (MO) site; it has no ROW.").format(self.ug_site))
		if site and site.row_required == "No":
			frappe.throw(_("ROW is marked not required on site {0}.").format(self.ug_site))

	def validate_duplicate(self):
		other = frappe.db.exists(
			"ROW Application",
			{"ug_site": self.ug_site, "row_authority": self.row_authority, "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(
				_("Site {0} already has ROW Application {1} for {2}. Reapply on that record instead.").format(
					self.ug_site, other, self.row_authority
				)
			)

	def track_attempts(self):
		previous = self.get_doc_before_save()
		if previous and previous.permission_status == "Rejected" and self.permission_status == "Reapplied":
			self.attempt_no = cint(self.attempt_no or 1) + 1

	def set_calculated(self):
		if self.bg_renewals:
			self.bg_end_date = max(getdate(r.new_end_date) for r in self.bg_renewals if r.new_end_date)
		end = self.permission_date if self.permission_status == "Received" and self.permission_date else today()
		self.row_ageing = date_diff(end, self.application_date) if self.application_date else 0
		self.sla_breached = int(bool(self.application_date) and self.row_ageing > cint(self.expected_days or 40))
		self.sd_status = self.get_sd_status()
		self.bg_status = self.get_bg_status()

	def get_sd_status(self):
		if not self.sd_required:
			return "Not Required"
		if self.sd_refund_received_date:
			return "Refunded"
		if self.sd_refund_applied_date:
			return "Refund Applied"
		return "Deposited" if self.sd_deposit_date else "Pending Deposit"

	def get_bg_status(self):
		if not self.bg_required:
			return "Not Required"
		if self.bg_released_date:
			return "Released"
		if not self.bg_end_date:
			return "Active"
		if getdate(self.bg_end_date) < getdate(today()):
			return "Expired"
		if getdate(self.bg_end_date) <= getdate(add_days(today(), cint(get_setting("bg_expiry_alert_days")))):
			return "Expiring"
		return "Active"


def refresh_ageing(name):
	"""Nightly: ageing, SLA flag and BG status change with the date, without anyone saving."""
	doc = frappe.get_doc("ROW Application", name)
	doc.set_calculated()
	doc.db_set(
		{"row_ageing": doc.row_ageing, "sla_breached": doc.sla_breached, "bg_status": doc.bg_status},
		update_modified=False,
	)
