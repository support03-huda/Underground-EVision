# Copyright (c) 2026, huda and contributors
"""UG Material Order — material ordered from Airtel by email, split by site, and its receipt
at the zone warehouse. The MRN No is the record name. Lines made from a Material Request keep
its name, and the request follows the order (Ordered)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from underground.underground.doctype.ug_site.ug_site import refresh_site


class UGMaterialOrder(Document):
	def validate(self):
		validate_sites_have_vlc(self.items)
		validate_requests(self.items)
		ordered = sum(flt(row.ordered_qty) for row in self.items)
		received = sum(flt(row.received_qty) for row in self.items)
		if not received:
			self.status = "Ordered"
		elif all(flt(row.received_qty) >= flt(row.ordered_qty) for row in self.items) and received >= ordered:
			self.status = "Received"
		else:
			self.status = "Partly Received"
		if received and not self.material_received_date:
			frappe.throw(_("Enter the Material Received Date for the quantities received."))

	def on_update(self):
		refresh_item_sites(self)
		update_requests(self)

	def after_delete(self):
		refresh_item_sites(self)
		update_requests(self)


def validate_requests(items):
	for row in items:
		if not row.material_request:
			continue
		site, status = frappe.db.get_value("UG Material Request", row.material_request, ["ug_site", "status"])
		if site != row.ug_site:
			frappe.throw(_("Row {0}: Material Request {1} is for site {2}, not {3}.").format(
				row.idx, row.material_request, site, row.ug_site))
		if status in ("Draft", "Rejected"):
			frappe.throw(_("Row {0}: Material Request {1} is {2}, not sent to the Material Team.").format(
				row.idx, row.material_request, _(status)))


def update_requests(doc):
	from underground.underground.doctype.ug_material_request.ug_material_request import update_from_orders

	requests = {row.material_request for row in doc.items}
	previous = doc.get_doc_before_save()
	if previous:
		requests |= {row.material_request for row in previous.items}
	update_from_orders(requests)


def validate_sites_have_vlc(items):
	"""A material order cannot be raised for a site without a VLC Code."""
	for site in {row.ug_site for row in items}:
		vlc_code, is_mobilization = frappe.db.get_value("UG Site", site, ["vlc_code", "is_mobilization"])
		if is_mobilization:
			frappe.throw(_("{0} is a Mobilization (MO) site; it has no material.").format(site))
		if not vlc_code:
			frappe.throw(_("Site {0} has no VLC Code yet; material can be ordered only after the VLC is received.").format(site))


def refresh_item_sites(doc):
	"""Refresh the material rollup of every site on this record, before and after the change."""
	sites = {row.ug_site for row in doc.items}
	previous = doc.get_doc_before_save()
	if previous:
		sites |= {row.ug_site for row in previous.items}
	for site in sites:
		refresh_site(site)
