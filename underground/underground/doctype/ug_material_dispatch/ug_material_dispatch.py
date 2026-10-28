# Copyright (c) 2026, huda and contributors
"""UG Material Dispatch — material sent from the warehouse to a vendor / team or site, split by site.
A fibre cable drum is dispatched with its Cable ID and start / end meter readings."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from underground.underground.doctype.ug_material_order.ug_material_order import (
	refresh_item_sites,
	validate_sites_have_vlc,
)


class UGMaterialDispatch(Document):
	def validate(self):
		validate_sites_have_vlc(self.items)
		if self.dispatch_to_type == "Vendor / Team" and not self.dispatch_to_vendor:
			frappe.throw(_("Select the Vendor / Team the material is dispatched to."))
		for row in self.items:
			row.cable_id = (row.cable_id or "").strip() or None
			if flt(row.end_reading):
				row.qty = abs(flt(row.end_reading) - flt(row.start_reading))
			if (flt(row.start_reading) or flt(row.end_reading)) and not row.cable_id:
				frappe.throw(_("Row {0}: enter the Cable ID / Drum No for the cable readings.").format(row.idx))

	def on_update(self):
		from underground.underground.doctype.ug_material_request.ug_material_request import mark_dispatched

		refresh_item_sites(self)
		if self.dispatched:
			mark_dispatched({row.ug_site for row in self.items})

	def after_delete(self):
		refresh_item_sites(self)
