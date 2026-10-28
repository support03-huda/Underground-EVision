# Copyright (c) 2026, huda and contributors
"""UG Punch Point — one Airtel punch point (a line of the ATC Tracker).

Field punch points are cleared by the PM and execution team with site photos; Airtel, ROW,
mail and document punch points are cleared by the ATC Manager. Evidence is required to close."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, today

from underground.underground.doctype.ug_site.ug_site import refresh_site

FIELD_CLOSERS = {"UG Project Manager", "UG Execution Team", "UG ATC Manager", "UG Admin", "System Manager"}
OTHER_CLOSERS = {"UG ATC Manager", "UG Admin", "System Manager"}


class UGPunchPoint(Document):
	def validate(self):
		if self.status == "Closed":
			self.validate_closure()
		else:
			self.nc_resolved_date = None
		self.set_ageing()

	def validate_closure(self):
		previous = self.get_doc_before_save()
		if previous and previous.status == "Closed":
			return
		closers = FIELD_CLOSERS if self.pp_group == "Field" else OTHER_CLOSERS
		if frappe.session.user != "Administrator" and not closers & set(frappe.get_roles()):
			frappe.throw(
				_("{0} punch points are closed by: {1}.").format(
					self.pp_group or _("This"), ", ".join(sorted(closers - {"System Manager"}))
				),
				frappe.PermissionError,
			)
		if not (self.evidence or self.evidence_photos):
			frappe.throw(_("Attach evidence before closing the punch point."))
		self.nc_resolved_date = self.nc_resolved_date or today()

	def set_ageing(self):
		self.current_ageing = date_diff(self.nc_resolved_date or today(), self.date_assigned) if self.date_assigned else 0

	def on_update(self):
		refresh_site(self.ug_site)
		previous = self.get_doc_before_save()
		if previous and previous.ug_site != self.ug_site:
			refresh_site(previous.ug_site)

	def after_delete(self):
		refresh_site(self.ug_site)
