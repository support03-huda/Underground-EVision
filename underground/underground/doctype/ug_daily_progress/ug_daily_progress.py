# Copyright (c) 2026, huda and contributors
"""UG Daily Progress — what the field team finished on one site in one day."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from underground.underground.doctype.ug_site.ug_site import refresh_site


class UGDailyProgress(Document):
	def validate(self):
		site = frappe.db.get_value(
			"UG Site",
			self.ug_site,
			["execution_release_date", "is_mobilization", "ibd_included", "work_type"],
			as_dict=True,
		)
		if not site.execution_release_date:
			frappe.throw(_("Site {0} has not been released for execution yet.").format(self.ug_site))
		if getdate(self.progress_date) < getdate(site.execution_release_date):
			frappe.throw(
				_("Progress date is before the site's Execution Release Date ({0}).").format(
					frappe.format(site.execution_release_date, {"fieldtype": "Date"})
				)
			)
		other = frappe.db.exists(
			"UG Daily Progress",
			{"ug_site": self.ug_site, "progress_date": self.progress_date, "name": ("!=", self.name)},
		)
		if other:
			frappe.throw(_("A Daily Progress for this site and date already exists: {0}.").format(other))
		if flt(self.td_km) < 0 or flt(self.cable_blowing_km) < 0 or flt(self.ibd_m) < 0:
			frappe.throw(_("Progress cannot be negative."))
		self.show_ibd = int(bool(site.ibd_included) or site.work_type in ("IBD", "FTTB"))

	def on_update(self):
		refresh_site(self.ug_site)
		previous = self.get_doc_before_save()
		if previous and previous.ug_site != self.ug_site:
			refresh_site(previous.ug_site)

	def after_delete(self):
		refresh_site(self.ug_site)
