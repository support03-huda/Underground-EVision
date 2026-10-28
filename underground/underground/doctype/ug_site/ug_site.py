# Copyright (c) 2026, huda and contributors
"""UG Site — one Airtel underground fiber site (node), from PO receipt (Day 0) to handover.

Calculated fields are rebuilt on every save, and by `refresh_site` whenever a linked ROW
Application, Daily Progress, Material Order / Dispatch or Punch Point changes (and nightly,
for ageing). `validate` refuses steps taken out of order (the process gates)."""

import json
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Count, Sum
from frappe.utils import cint, date_diff, flt, today

from underground.utils import get_setting, get_stage_sla

STAGES = [
	"1 - PO Receipt",
	"2 - KMZ and Team",
	"3 - Survey and Feasibility",
	"4 - SLD and Exceptions",
	"5 - CWIP, ROW, Job ID, VLC",
	"6 - Material",
	"7 - Execution",
	"8 - FF1, PP, ATC",
	"9 - Closure and Billing",
]
ROW_SUBMITTED = ("Submitted", "Acknowledged")
PO_LINE_FIELDS = ("line_item", "description", "qty", "uom", "civil_length", "optical_length", "rate", "amount")
# Fields the site-linked records fetch and keep in step with the site.
PROPAGATED_FIELDS = ("pm_user", "am_user", "node_id", "node_name")
LINKED_DOCTYPES = ("ROW Application", "UG Daily Progress", "UG Punch Point", "UG Material Request")
# People assigned to a site who must approve it: site field, approval field prefix, their master
# record, and the site field holding their login.
ASSIGNMENTS = {
	"Area Manager": {"field": "area_manager", "prefix": "am", "doctype": "UG Employee",
	                 "name_field": "employee_name", "user_field": "am_user"},
	"Splicer": {"field": "splicer", "prefix": "splicer", "doctype": "UG Splicer",
	            "name_field": "splicer_name", "user_field": "splicer_user"},
}


class UGSite(Document):
	def validate(self):
		self.fill_from_kmz()
		self.assign_area_manager()
		self.validate_area_manager()
		self.set_splicing_vendor()
		self.request_approvals()
		self.check_cable_ids()
		self.node_id = (self.node_id or "").strip() or None
		self.validate_node_id()
		self.track_po_revision()
		self.standard_trench_depth = flt(get_setting("standard_trench_depth"))
		self.update_rollups()
		self.validate_gates()

	def on_update(self):
		self.register_airtel_po()
		for kind in self.flags.approval_requests or []:
			send_assignment_request(self, kind)
		if self.flags.notify_vendor:
			notify_splicing_vendor(self)
		changed = {f: self.get(f) for f in PROPAGATED_FIELDS if self.has_value_changed(f)}
		if changed and not self.flags.in_insert:
			for doctype in LINKED_DOCTYPES:
				frappe.db.set_value(doctype, {"ug_site": self.name}, changed, update_modified=False)

	def fill_from_kmz(self):
		"""Read a newly attached KMZ here: the Attach field saves the form right after upload,
		so values filled in the browser would be overwritten by that save."""
		if not self.kmz_file or (self.kmz_map and not self.has_value_changed("kmz_file")):
			return
		if not self.kmz_file.lower().endswith((".kmz", ".kml")):
			return
		try:
			data = parse_kmz_file(self.kmz_file)
		except frappe.ValidationError as e:
			frappe.msgprint(str(e), title=_("KMZ not read"), indicator="orange")
			return
		self.update({
			"kmz_latitude": data["latitude"],
			"kmz_longitude": data["longitude"],
			"kmz_tapping_point": data["tapping_point"],
			"kmz_tapping_distance": data["tapping_distance"],
			"kmz_route_length": data["proposed_length"],
			"kmz_existing_route_length": data["existing_length"],
			"kmz_map": data["map"],
			"kmz_received": 1,
			"kmz_received_date": self.kmz_received_date or today(),
		})
		notes = []
		if data["node_id"] and not self.node_id:
			self.node_id = data["node_id"]
		elif data["node_id"] and data["node_id"] != (self.node_id or "").strip():
			notes.append(_("This KMZ is for node {0}, but the site is node {1}. Check the file.").format(
				data["node_id"], self.node_id))
		if flt(self.po_civil_length) and data["proposed_length"] > flt(self.po_civil_length):
			notes.append(_("KMZ route {0} m is more than the PO civil length {1} m: a length extension of about {2} m is needed.").format(
				data["proposed_length"], flt(self.po_civil_length), round(data["proposed_length"] - flt(self.po_civil_length))))
		frappe.msgprint(
			_("Read KMZ: proposed route {0} m, tapping point {1} m from site.").format(
				data["proposed_length"], data["tapping_distance"] or "?") + (" " + " ".join(notes) if notes else ""),
			indicator="orange" if notes else "green",
			alert=True,
		)

	def assign_area_manager(self):
		"""Give the site its area and Area Manager from its location (survey, else KMZ).
		A manager picked by a person is kept; one picked by the system follows the location."""
		from underground.underground.doctype.ug_zone.ug_zone import find_zone

		if self.has_value_changed("area_manager"):
			self.area_manager_by_system = 0
		lat = flt(self.survey_latitude) or flt(self.kmz_latitude)
		lon = flt(self.survey_longitude) or flt(self.kmz_longitude)
		moved = any(
			self.has_value_changed(f)
			for f in ("survey_latitude", "survey_longitude", "kmz_latitude", "kmz_longitude")
		)
		if self.area_manager and not (self.area_manager_by_system and moved):
			return

		if lat and lon:
			zone, how = find_zone(lat, lon)
			if zone and not self.zone:
				self.zone = zone
			elif zone and zone != self.zone:
				frappe.msgprint(
					_("The site location is in area {0} ({1}), but the site's area is {2}. The Area Manager is taken from {2}.").format(
						zone, how, self.zone),
					indicator="orange",
					alert=True,
				)
		if not self.zone:
			if not (lat and lon):
				return
			frappe.msgprint(
				_("No area found for this location. Add the area boundary or centre in UG Zone, or pick the area by hand."),
				indicator="orange",
				alert=True,
			)
			return
		manager = pick_area_manager(self.zone)
		if not manager:
			frappe.msgprint(
				_("No active Area Manager for area {0}. Add one in UG Employee (Designation: Area Manager, Zone / Area: {0}).").format(
					self.zone),
				indicator="orange",
				alert=True,
			)
		elif manager != self.area_manager:
			self.area_manager = manager
			self.area_manager_by_system = 1
			frappe.msgprint(
				_("Area {0} and Area Manager {1} set from the site location.").format(self.zone, manager),
				indicator="green",
				alert=True,
			)

	def validate_area_manager(self):
		if not (self.area_manager and self.zone):
			return
		manager_zone = frappe.db.get_value("UG Employee", self.area_manager, "zone")
		if manager_zone and manager_zone != self.zone:
			frappe.throw(
				_("Area Manager {0} looks after area {1}, but this site is in area {2}. Pick an Area Manager of {2}.").format(
					self.area_manager, manager_zone, self.zone),
				title=_("Wrong Area Manager"),
			)

	def set_splicing_vendor(self):
		"""The splicing vendor (by default the execution vendor) assigns the splicer, from its own splicers."""
		if not self.splicing_vendor and self.execution_vendor:
			self.splicing_vendor = self.execution_vendor
		if self.splicing_vendor and self.splicer:
			splicer_vendor = frappe.db.get_value("UG Splicer", self.splicer, "vendor")
			if splicer_vendor and splicer_vendor != self.splicing_vendor:
				frappe.throw(
					_("Splicer {0} works for {1}, but the splicing vendor of this site is {2}.").format(
						self.splicer, splicer_vendor, self.splicing_vendor),
					title=_("Wrong Splicer"),
				)
		self.flags.notify_vendor = bool(
			self.splicing_vendor and not self.splicer and self.has_value_changed("splicing_vendor")
		)

	def check_cable_ids(self):
		"""Warn about a cable ID laid on the site that was never dispatched to it."""
		ids = {(row.cable_id or "").strip() for row in self.cable_logs} - {""}
		if not ids or self.is_new():
			return
		dispatch_item = frappe.qb.DocType("UG Material Dispatch Item")
		dispatched = (
			frappe.qb.from_(dispatch_item)
			.select(dispatch_item.cable_id)
			.distinct()
			.where((dispatch_item.ug_site == self.name) & dispatch_item.cable_id.isnotnull())
			.run(pluck=True)
		)
		unknown = sorted(ids - {(c or "").strip() for c in dispatched})
		if unknown:
			frappe.msgprint(
				_("Cable ID {0} was not dispatched to this site. Check the ID, or the Material Dispatch.").format(
					", ".join(unknown)),
				indicator="orange",
				alert=True,
			)

	def request_approvals(self):
		"""A newly assigned Area Manager or Splicer, or a new KMZ on a site they hold, needs their
		approval: mark it pending and send the request (with the KMZ) after saving."""
		self.flags.approval_requests = []
		for kind, a in ASSIGNMENTS.items():
			p = a["prefix"]
			if not self.get(a["field"]):
				self.update({f"{p}_approval_status": None, f"{p}_request_date": None, f"{p}_approved_on": None,
				             f"{p}_closed_on": None, f"{p}_approval_remarks": None})
				continue
			open_ = self.get(f"{p}_approval_status") in ("Pending", "In Progress")
			new_kmz = self.kmz_file and self.has_value_changed("kmz_file") and open_
			if self.has_value_changed(a["field"]) or new_kmz:
				self.update({f"{p}_approval_status": "Pending", f"{p}_request_date": today(),
				             f"{p}_approved_on": None, f"{p}_closed_on": None, f"{p}_approval_remarks": None})
				self.flags.approval_requests.append(kind)

	# ------------------------------------------------------------ identity and PO
	def register_airtel_po(self):
		"""A PO PDF attached here (instead of through Airtel PO) is still filed as an Airtel PO record."""
		if not (self.po_copy or "").lower().endswith(".pdf") or not self.po_lines:
			return
		if not (self.flags.in_insert or self.has_value_changed("po_copy")):
			return
		if all(row.airtel_po for row in self.po_lines):
			return
		from underground.underground.doctype.airtel_po.airtel_po import LINE_FIELDS, parse_file

		try:
			data = parse_file(self.po_copy)
		except Exception:
			frappe.clear_last_message()
			return
		if self.po_number not in (data.get("po_number"), data["po_no"]):
			return
		if not frappe.db.exists("Airtel PO", data["po_no"]):
			frappe.get_doc(
				{
					"doctype": "Airtel PO",
					"po_file": self.po_copy,
					"status": "Applied",
					"po_receipt_date": self.po_receipt_date,
					"po_type": data["po_type"],
					**{f: data.get(f) for f in ("po_number", "po_no", "po_date", "rev_no", "rev_date",
					                           "internal_ref", "buyer_name", "old_po_ref", "total_value", "payment_terms")},
					"lines": [{**{f: line.get(f) for f in LINE_FIELDS}, "ug_site": self.name} for line in data["lines"]],
				}
			).insert(ignore_permissions=True)
		for row in self.po_lines:
			if not row.airtel_po:
				row.db_set("airtel_po", data["po_no"], update_modified=False)

	def validate_node_id(self):
		if self.node_id and frappe.db.exists("UG Site", {"node_id": self.node_id, "name": ("!=", self.name)}):
			other = frappe.db.get_value("UG Site", {"node_id": self.node_id}, "name")
			frappe.throw(_("Node ID {0} is already used by site {1}.").format(frappe.bold(self.node_id), other))

	def track_po_revision(self):
		"""A revised PO overwrites PO Number; the previous PO and its lines move to PO History."""
		if not self.original_po_number:
			self.original_po_number = self.po_number
		previous = self.get_doc_before_save()
		if not previous or not previous.po_number or previous.po_number == self.po_number:
			return
		self.append(
			"po_history",
			{
				"po_number": previous.po_number,
				"replaced_on": today(),
				"po_amount": previous.po_amount,
				"civil_length": previous.po_civil_length,
				"optical_length": previous.po_optical_length,
				"lines": json.dumps([{k: line.get(k) for k in PO_LINE_FIELDS} for line in previous.po_lines]),
			},
		)
		self.revised_po_date = self.revised_po_date or today()

	# ------------------------------------------------------------ calculated fields
	def update_rollups(self):
		self.set_po_totals()
		self.set_ageing()
		self.set_survey_flags()
		self.set_row_rollup()
		self.set_progress_rollup()
		self.set_material_rollup()
		self.set_pp_rollup()
		self.set_billing()
		self.set_stage()

	def set_po_totals(self):
		"""Superseded lines (replaced by a later PO) are left out; Mobilization lines make the MO amount."""
		for line in self.po_lines:
			line.amount = flt(line.qty) * flt(line.rate)
		active = [line for line in self.po_lines if not line.superseded]
		work = [line for line in active if line.scope != "Mobilization"]
		mobilization = [line for line in active if line.scope == "Mobilization"]
		self.po_amount = sum(flt(line.amount) for line in work)
		self.po_civil_length = sum(flt(line.civil_length) for line in work)
		self.po_optical_length = sum(flt(line.optical_length) for line in work)
		if mobilization:
			self.mo_po_amount = sum(flt(line.amount) for line in mobilization)
		if not flt(self.td_scope_km) and self.po_civil_length:
			self.td_scope_km = self.po_civil_length / 1000

	def set_ageing(self):
		start = self.po_receipt_date
		end = self.handover_date if self.handover_status == "Handed Over" and self.handover_date else today()
		self.site_ageing = date_diff(end, start) if start else 0
		if self.kmz_received and self.kmz_received_date and start:
			self.kmz_ageing = date_diff(self.kmz_received_date, start)
		else:
			self.kmz_ageing = self.site_ageing
		self.kmz_overdue = int(
			not self.kmz_received and not self.is_mobilization and self.kmz_ageing > cint(get_setting("kmz_due_day"))
		)

	def set_survey_flags(self):
		route_length = flt(self.survey_length) or flt(self.kmz_route_length)
		self.length_extension_required = int(route_length > flt(self.po_civil_length) > 0)
		self.truncation_required = int(self.site_feasibility == "Not Feasible")
		if self.truncation_required and self.truncation_status in (None, "", "Not Required"):
			self.truncation_status = "Requested"
			self.truncation_request_date = self.truncation_request_date or today()
		for status, date in (
			("length_extension_status", "length_extension_request_date"),
			("rate_revision_status", "rate_revision_request_date"),
		):
			if self.get(status) == "Requested" and not self.get(date):
				self.set(date, today())

	def set_row_rollup(self):
		apps = []
		if not self.is_new():
			apps = frappe.get_all(
				"ROW Application",
				filters={"ug_site": self.name},
				fields=[
					"name",
					"row_authority",
					"application_status",
					"permission_status",
					"sd_required",
					"sd_amount",
					"sd_refund_received_date",
					"bg_required",
					"bg_amount",
					"bg_released_date",
				],
			)
		self.row_count = len(apps)
		self.flags.row_submitted = any(a.application_status in ROW_SUBMITTED for a in apps)
		if self.row_required == "No":
			status = "Not Required"
		elif not apps:
			status = "Pending" if self.row_required == "Yes" else ""
		elif any(a.permission_status == "Rejected" for a in apps):
			status = "Rejected"
		elif all(a.permission_status == "Received" for a in apps):
			status = "All Received"
		else:
			status = "Pending"
		self.row_overall_status = status
		self.sd_bg_outstanding = sum(
			flt(a.sd_amount) for a in apps if a.sd_required and not a.sd_refund_received_date
		) + sum(flt(a.bg_amount) for a in apps if a.bg_required and not a.bg_released_date)
		by_authority = {a.row_authority: a.name for a in apps}
		for row in self.row_authorities:
			row.row_application = by_authority.get(row.row_authority)

	def set_progress_rollup(self):
		td = blowing = ibd = 0
		if not self.is_new():
			dpr = frappe.qb.DocType("UG Daily Progress")
			td, blowing, ibd = (
				frappe.qb.from_(dpr)
				.select(Sum(dpr.td_km), Sum(dpr.cable_blowing_km), Sum(dpr.ibd_m))
				.where(dpr.ug_site == self.name)
				.run()[0]
			)
		self.td_cumulative_km = flt(td, 3)
		self.td_balance_km = flt(flt(self.td_scope_km) - flt(td), 3)
		self.cable_blowing_cumulative_km = flt(blowing, 3)
		self.ibd_done_m = flt(ibd)

	def set_material_rollup(self):
		received, dispatched = {}, {}
		if not self.is_new():
			order_item = frappe.qb.DocType("UG Material Order Item")
			received = dict(
				frappe.qb.from_(order_item)
				.select(order_item.item, Sum(order_item.received_qty))
				.where((order_item.ug_site == self.name) & (order_item.parenttype == "UG Material Order"))
				.groupby(order_item.item)
				.run()
			)
			dispatch = frappe.qb.DocType("UG Material Dispatch")
			dispatch_item = frappe.qb.DocType("UG Material Dispatch Item")
			dispatched = dict(
				frappe.qb.from_(dispatch_item)
				.join(dispatch)
				.on(dispatch.name == dispatch_item.parent)
				.select(dispatch_item.item, Sum(dispatch_item.qty))
				.where(
					(dispatch_item.ug_site == self.name)
					& (dispatch_item.parenttype == "UG Material Dispatch")
					& (dispatch.dispatched == 1)
				)
				.groupby(dispatch_item.item)
				.run()
			)
		# Fibre cable laid: the length between the start and end meter readings of each drum.
		laid = {}
		for row in self.cable_logs:
			row.length_m = abs(flt(row.end_reading) - flt(row.start_reading)) if flt(row.end_reading) else 0
			laid[row.item] = laid.get(row.item, 0) + row.length_m
		existing = {row.item for row in self.site_materials}
		for item in list(received) + list(dispatched) + list(laid):
			if item not in existing:
				self.append("site_materials", {"item": item, "uom": frappe.db.get_value("UG Material Item", item, "uom")})
				existing.add(item)
		for row in self.site_materials:
			row.received_qty = flt(received.get(row.item))
			row.dispatched_qty = flt(dispatched.get(row.item))
			if row.item in laid:
				row.consumed_qty = flt(laid[row.item], 1)
			row.balance_qty = row.received_qty - flt(row.consumed_qty)
		self.material_dispatched = int(any(flt(qty) > 0 for qty in dispatched.values()))
		self.material_received_qty = sum(flt(row.received_qty) for row in self.site_materials)
		self.material_consumed_qty = sum(flt(row.consumed_qty) for row in self.site_materials)
		self.material_balance_qty = self.material_received_qty - self.material_consumed_qty

	def set_pp_rollup(self):
		pps = []
		if not self.is_new():
			pps = frappe.get_all(
				"UG Punch Point", filters={"ug_site": self.name}, fields=["status", "pp_group", "nc_resolved_date"]
			)
		self.total_pp = len(pps)
		self.open_pp = sum(1 for pp in pps if pp.status != "Closed")
		self.field_pp = sum(1 for pp in pps if pp.pp_group == "Field")
		self.row_mail_doc_pp = self.total_pp - self.field_pp
		if not self.total_pp:
			self.pp_closure_status = "No PP"
		elif self.open_pp == self.total_pp:
			self.pp_closure_status = "Open"
		elif self.open_pp:
			self.pp_closure_status = "Partially Closed"
		else:
			self.pp_closure_status = "All Closed"
		resolved = [pp.nc_resolved_date for pp in pps if pp.nc_resolved_date]
		self.pp_closure_date = max(resolved) if self.pp_closure_status == "All Closed" and resolved else None

	def set_billing(self):
		self.billing_ready = int(
			not self.is_mobilization
			and self.pp_closure_status in ("No PP", "All Closed")
			and self.atc_status in ("Ready", "Approved")
			and self.reconciliation_status == "Approved"
			and self.zonal_approval_status == "Approved"
			and self.central_approval_status == "Approved"
		)
		if flt(self.invoice_amount) and not flt(self.retention_amount):
			self.retention_amount = flt(self.invoice_amount) * flt(get_setting("retention_percent")) / 100

		if self.is_mobilization:
			self.final_ug_status = "Billing Only"
		elif self.truncation_status == "Closed":
			self.final_ug_status = "Truncated"
		elif self.handover_status == "Handed Over" and self.billing_ready:
			self.final_ug_status = "Completed"
		else:
			self.final_ug_status = "Active"

	def set_stage(self):
		self.current_stage = self.get_stage()
		end_day, _owner = get_stage_sla(self.current_stage) if self.current_stage in STAGES else (None, None)
		self.stage_sla_end_day = cint(end_day)
		self.stage_overdue = int(bool(end_day) and self.site_ageing > cint(end_day))
		self.current_execution_stage = self.get_execution_stage()

	def get_stage(self):
		if self.final_ug_status == "Billing Only":
			return "MO - Billing Only"
		if self.final_ug_status in ("Truncated", "Completed"):
			return self.final_ug_status
		if self.atc_status in ("Ready", "Approved") or self.handover_status == "Handed Over":
			return STAGES[8]
		if self.ff1_submission_status not in (None, "", "Pending") or self.total_pp:
			return STAGES[7]
		if self.execution_release_date:
			return STAGES[6]
		if self.vlc_code:
			return STAGES[5]
		if self.cwip_id or self.row_count or self.job_id or self.airtel_works_upload_status == "Accepted":
			return STAGES[4]
		if self.site_feasibility == "Feasible":
			return STAGES[3]
		if self.kmz_received:
			return STAGES[2]
		if self.po_lines:
			return STAGES[1]
		return STAGES[0]

	def get_execution_stage(self):
		if self.is_mobilization or not self.execution_start_date:
			return ""
		if self.atc_status in ("Ready", "Approved"):
			return "ATC"
		if self.total_pp:
			return "PP"
		if self.ff1_submission_status not in (None, "", "Pending"):
			return "FF1"
		if self.otdr_status not in (None, "", "Pending"):
			return "Testing"
		if self.splicing_status not in (None, "", "Pending"):
			return "Splicing"
		if flt(self.cable_blowing_cumulative_km):
			return "Cable Blowing"
		return "T&D"

	# ------------------------------------------------------------ process gates
	def changed(self, fieldname):
		"""True when `fieldname` is being set or changed by this save."""
		previous = self.get_doc_before_save()
		if not previous:
			return bool(self.get(fieldname))
		return self.get(fieldname) != previous.get(fieldname)

	def validate_gates(self):
		if self.site_feasibility == "Not Feasible" and not (self.non_feasibility_reason or "").strip():
			frappe.throw(_("Enter the Non-Feasibility Reason before marking the site Not Feasible."))
		if self.row_required == "No" and not (self.row_not_required_reason or "").strip():
			frappe.throw(_("Enter the reason ROW is not required."))
		if self.is_mobilization:
			return

		if self.job_id and self.changed("job_id") and self.row_required != "No" and not self.flags.row_submitted:
			frappe.throw(
				_("Job ID can be entered only after at least one ROW Application is submitted, or ROW is marked not required.")
			)
		if self.vlc_code and self.changed("vlc_code") and not (self.job_id and self.job_id_approval_status == "Approved"):
			frappe.throw(_("VLC Code can be entered only after the Job ID is approved by Airtel."))
		if self.execution_release_date and self.changed("execution_release_date"):
			self.validate_release()
		self.validate_depth_deviations()
		if self.ff1_submission_status != "Pending" and self.changed("ff1_submission_status"):
			self.validate_ff1()
		if self.central_approval_status == "Approved" and self.changed("central_approval_status"):
			if self.zonal_approval_status != "Approved":
				frappe.throw(_("Central Approval follows Zonal Approval: get the zonal approval first."))
		invoice_fields = ("billing_status", "invoice_number", "invoice_date", "invoice_amount")
		if not self.billing_ready and any(self.changed(f) for f in invoice_fields):
			if self.billing_status != "Pending" or self.invoice_number or self.invoice_date or flt(self.invoice_amount):
				frappe.throw(
					_("Invoice details can be entered only when the site is Billing Ready: all punch points closed, ATC ready, reconciliation approved, and zonal and central approvals received.")
				)
		if self.handover_status == "Handed Over" and self.changed("handover_status"):
			if self.pp_closure_status not in ("No PP", "All Closed"):
				frappe.throw(_("The site can be handed over only after all punch points are closed."))

	def validate_release(self):
		missing = []
		if self.row_overall_status not in ("All Received", "Not Required"):
			missing.append(_("ROW permissions all received (or ROW not required)"))
		if not self.job_id or self.job_id_mapping_status != "Correct":
			missing.append(_("Job ID mapped (mapping status Correct)"))
		if not self.material_dispatched:
			missing.append(_("material dispatched"))
		if not (self.execution_vendor or self.team_vendor):
			missing.append(_("execution vendor / team assigned"))
		if missing:
			frappe.throw(
				_("The site cannot be released for execution yet. Still needed:") + "<br>• " + "<br>• ".join(missing),
				title=_("Release gate"),
			)

	def validate_ff1(self):
		"""FF1 goes in with the required documents: test passed, ROW permission and final site photos."""
		missing = []
		if self.otdr_status != "Passed":
			missing.append(_("OTDR / Testing Passed"))
		if self.execution_documents_status != "Complete":
			missing.append(_("Execution Documents Complete"))
		if self.row_overall_status not in ("All Received", "Not Required"):
			missing.append(_("ROW permission received (or ROW not required)"))
		if self.final_photos_status != "Received":
			missing.append(_("final geo-tagged photos received"))
		if missing:
			frappe.throw(
				_("FF1 cannot be submitted yet. Still needed:") + "<br>• " + "<br>• ".join(missing),
				title=_("FF1 gate"),
			)

	def validate_depth_deviations(self):
		previous = self.get_doc_before_save()
		before = {row.name: flt(row.approved_depth) for row in previous.depth_deviations} if previous else {}
		for row in self.depth_deviations:
			if flt(row.approved_depth) and flt(row.approved_depth) != before.get(row.name):
				if row.status not in ("Approved", "Closed"):
					frappe.throw(
						_("Depth Deviation row {0}: a reduced depth can be recorded only after Airtel approves the stretch.").format(
							row.idx
						)
					)


def refresh_site(site):
	"""Recalculate a site's rollups and ageing without running the gates.

	Called when a linked record changes and by the nightly job."""
	if not site or not frappe.db.exists("UG Site", site):
		return
	doc = frappe.get_doc("UG Site", site)
	doc.update_rollups()
	doc.db_update()
	for table in ("row_authorities", "site_materials"):
		for row in doc.get(table):
			if row.get("__islocal") or not row.name:
				row.db_insert()
			else:
				row.db_update()
	doc.notify_update()


def guess_work_type(lines):
	"""Best guess from the PO lines; the user confirms it on the form."""
	scopes = {line.get("scope") for line in lines}
	text = " ".join(line.get("description") or "" for line in lines).lower()
	if scopes == {"Mobilization"}:
		return "MO"
	if scopes == {"IBD"}:
		return "IBD"
	if "back bone" in text or "backbone" in text:
		return "BB"
	if "quality" in text.split("connectivity")[-1]:
		return "Quality Patch"
	if "end to end execution" in text or "IBD" in scopes:
		return "LM"
	# The inter-city trenching rate card (e.g. ICW000004) is used for both backbone and last mile:
	# up to 1 km (the LM rate card's own "Length <=1Km" limit) it is a last mile, longer a backbone.
	if "inter city" in re.sub(r"[\s-]+", " ", text):
		length = sum(
			flt(line.get("qty"))
			for line in lines
			if line.get("scope") == "T&D" and (line.get("uom") or "").lower().startswith("met")
		)
		return "LM" if 0 < length <= 1000 else "BB"
	return None


@frappe.whitelist()
def read_po_copy(file_url, site=None):
	"""Values for the UG Site form from an attached Airtel PO PDF."""
	from underground.underground.doctype.airtel_po.airtel_po import find_site, parse_file, site_line

	frappe.has_permission("UG Site", "create" if not site else "write", throw=True)
	data = parse_file(file_url)
	lines = data["lines"]
	node_id = next((line["node_id"] for line in lines if line.get("node_id")), None)
	po_exists = frappe.db.exists("Airtel PO", data["po_no"])
	work_type = guess_work_type(lines)
	need_by = [line["need_by"] for line in lines if line.get("need_by")]
	existing_site = find_site(node_id)
	return {
		"po_number": data.get("po_number") or data["po_no"],
		"po_start_date": data.get("po_date"),
		"po_end_date": max(need_by) if need_by else None,
		"po_type": data["po_type"],
		"node_id": node_id,
		"cwip_id": next((line["cwip_id"] for line in lines if line.get("cwip_id")), None),
		"work_type": work_type if work_type and frappe.db.exists("UG Work Type", work_type) else None,
		"ibd_included": int(work_type == "LM" and any(line.get("scope") == "IBD" for line in lines)),
		"po_lines": [site_line(data["po_no"] if po_exists else None, data["po_type"], line) for line in lines],
		"total_value": data.get("total_value"),
		"existing_site": existing_site if existing_site != site else None,
	}


def send_assignment_request(site, kind):
	"""Email (with the KMZ attached) and in-app notification asking the assigned Area Manager or
	Splicer to approve the site."""
	from frappe.utils import get_url_to_form

	a = ASSIGNMENTS[kind]
	person = frappe.db.get_value(a["doctype"], site.get(a["field"]), [a["name_field"], "user"], as_dict=True)
	if not person:
		return
	name = person.get(a["name_field"])
	email = person.user and frappe.db.get_value("User", person.user, "email")
	if kind == "Area Manager":
		email = frappe.db.get_value("UG Employee", site.area_manager, "email") or email
	label = " ".join(filter(None, [site.node_id, site.node_name])) or site.name
	url = get_url_to_form("UG Site", site.name)
	lat = flt(site.survey_latitude) or flt(site.kmz_latitude)
	lon = flt(site.survey_longitude) or flt(site.kmz_longitude)
	by_system = kind == "Area Manager" and site.area_manager_by_system
	rows = [
		(_("Site"), f'<a href="{url}">{site.name}</a> ({label})'),
		(_("PO"), site.po_number),
		(_("Work Type"), site.work_type),
		(_("Area"), site.zone),
		(_("Area Manager"), site.area_manager if kind == "Splicer" else None),
		(_("Location"), f'<a href="https://www.google.com/maps?q={lat},{lon}">{lat:.6f}, {lon:.6f}</a>' if lat and lon else None),
		(_("Tapping Point"), site.kmz_tapping_point),
		(_("KMZ Proposed Route"), f"{flt(site.kmz_route_length):.0f} m" if site.kmz_route_length else None),
		(_("Survey Length"), f"{flt(site.survey_length):.0f} m" if site.survey_length else None),
		(_("PO Civil Length"), f"{flt(site.po_civil_length):.0f} m" if site.po_civil_length else None),
		(_("Assigned"), _("by the system, from the site location") if by_system
		 else _("by {0}").format(frappe.utils.get_fullname(frappe.session.user))),
	]
	table = "".join(
		f'<tr><td style="padding:4px 12px 4px 0;color:#666">{k}</td><td style="padding:4px 0"><b>{v}</b></td></tr>'
		for k, v in rows if v
	)
	kmz_note = _("The KMZ is attached.") if site.kmz_file else _("No KMZ is attached to the site yet.")
	subject = _("Approval needed: site {0} assigned to you as {1}").format(label, _(kind))
	message = (
		f"<p>{_('Dear {0},').format(name)}</p>"
		f"<p>{_('This site has been assigned to you as {0}. Please check the route and approve or reject it.').format(_(kind))}</p>"
		f"<table>{table}</table><p>{kmz_note}</p>"
		f'<p><a href="{url}">{_("Open the site")}</a> {_("and use {0} → Approve or Reject.").format(_(kind))}</p>'
	)

	if person.user:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": person.user,
				"type": "Alert",
				"document_type": "UG Site",
				"document_name": site.name,
				"subject": subject[:140],
				"email_content": message,
			}
		).insert(ignore_permissions=True)
	if email and cint(get_setting("send_emails")):
		attachments = []
		if site.kmz_file:
			file_doc = frappe.get_doc("File", {"file_url": site.kmz_file})
			attachments.append({"fname": file_doc.file_name, "fcontent": file_doc.get_content()})
		frappe.sendmail(
			recipients=[email],
			subject=subject[:140],
			message=message,
			attachments=attachments,
			reference_doctype="UG Site",
			reference_name=site.name,
		)
	if email or person.user:
		frappe.msgprint(_("Approval request sent to {0} {1}.").format(_(kind), name), alert=True)
	else:
		frappe.msgprint(
			_("{0} {1} has no email or ERP user in {2}: the approval request was not sent.").format(
				_(kind), name, _(a["doctype"])),
			indicator="orange",
		)


@frappe.whitelist()
def respond_assignment(site, kind, approve, remarks=None):
	"""The site's Area Manager or Splicer approves (it moves to In Progress) or rejects it with a
	reason. Admin, Back Office and the PM are told either way; on a rejection they assign someone else."""
	doc, a = get_assignment(site, kind)
	p = a["prefix"]
	if doc.get(f"{p}_approval_status") != "Pending":
		frappe.throw(_("There is no pending {0} assignment on this site.").format(_(kind)))
	approve = cint(approve)
	remarks = (remarks or "").strip()
	if not approve and not remarks:
		frappe.throw(_("Give the reason for rejecting."))
	status = "In Progress" if approve else "Rejected"
	doc.db_set({f"{p}_approval_status": status, f"{p}_approved_on": today(), f"{p}_approval_remarks": remarks})
	note = _("{0} {1}: {2}.").format(_(kind), doc.get(a["field"]), _("approved, work in progress") if approve else _("rejected"))
	if remarks:
		note += " " + _("Remarks: {0}").format(frappe.utils.escape_html(remarks))
	doc.add_comment("Comment", note)
	label = doc.node_id or doc.name
	if approve:
		notify_assignment_change(doc, kind, _("{0} approved site {1}: in progress").format(_(kind), label), note)
	else:
		notify_assignment_change(doc, kind, _("{0} rejected site {1}").format(_(kind), label), note,
		                         _("assign another {0}").format(_(kind)))
	return status


@frappe.whitelist()
def close_assignment(site, kind, remarks=None):
	"""The Area Manager or Splicer closes their in-progress assignment once their work is done."""
	doc, a = get_assignment(site, kind)
	p = a["prefix"]
	if doc.get(f"{p}_approval_status") != "In Progress":
		frappe.throw(_("Only an In Progress assignment can be closed."))
	if kind == "Splicer" and doc.splicing_status != "Completed":
		frappe.throw(_("Set Splicing Status to Completed on the site before closing."))
	remarks = (remarks or "").strip()
	doc.db_set({
		f"{p}_approval_status": "Closed",
		f"{p}_closed_on": today(),
		f"{p}_approval_remarks": remarks or doc.get(f"{p}_approval_remarks"),
	})
	note = _("{0} {1} closed the assignment.").format(_(kind), doc.get(a["field"]))
	if remarks:
		note += " " + _("Remarks: {0}").format(frappe.utils.escape_html(remarks))
	doc.add_comment("Comment", note)
	notify_assignment_change(doc, kind, _("{0} closed site {1}").format(_(kind), doc.node_id or doc.name), note)
	return "Closed"


def get_assignment(site, kind):
	"""The site and its assignment settings, after checking the user may act on it."""
	if kind not in ASSIGNMENTS:
		frappe.throw(_("Unknown assignment {0}.").format(kind))
	a = ASSIGNMENTS[kind]
	doc = frappe.get_doc("UG Site", site)
	if frappe.session.user != doc.get(a["user_field"]):
		frappe.throw(_("Only the {0} of this site can do this.").format(_(kind)), frappe.PermissionError)
	return doc, a


def notify_assignment_change(doc, kind, subject, note, action=None):
	"""Tell the Admins, the Back Office and the PM (and, for a splicer, the Area Manager)."""
	from frappe.utils import get_url_to_form

	from underground.utils import get_role_users

	message = f'<p>{note}</p><p><a href="{get_url_to_form("UG Site", doc.name)}">{_("Open the site")}</a>'
	message += f" {_('and')} {action}.</p>" if action else "</p>"
	recipients = {"Administrator", *get_role_users("UG Admin", "UG Back Office"), doc.pm_user}
	if kind == "Splicer":
		recipients |= {doc.am_user, doc.vendor_user}
	recipients.discard(frappe.session.user)
	send_emails = cint(get_setting("send_emails"))
	for user in filter(None, recipients):
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": "UG Site",
				"document_name": doc.name,
				"subject": subject[:140],
				"email_content": message,
			}
		).insert(ignore_permissions=True)
		email = frappe.db.get_value("User", user, "email")
		if send_emails and email:
			frappe.sendmail(recipients=[email], subject=subject[:140], message=message,
			                reference_doctype="UG Site", reference_name=doc.name)


@frappe.whitelist()
def get_assignments():
	"""Rows for the Assignments board: one per Area Manager / Splicer assignment. Area Managers
	and Splicers get all of their own (pending ones to approve or reject). Everyone who sees all
	sites (Admin, Back Office, Management...) follows the others' work only once it is approved:
	In Progress and Closed. Only the assigned person acts on an assignment."""
	from underground.utils import sees_all_sites

	user = frappe.session.user
	if not frappe.has_permission("UG Site", "read"):
		return {"rows": [], "see_all": False, "has_own": False}
	see_all = sees_all_sites(user)
	fields = ["name", "node_id", "node_name", "zone", "work_type", "current_stage", "splicing_status",
	          "splicing_vendor", "vendor_user"]
	for a in ASSIGNMENTS.values():
		p = a["prefix"]
		fields += [a["field"], a["user_field"], f"{p}_approval_status", f"{p}_request_date", f"{p}_approved_on",
		           f"{p}_closed_on", f"{p}_approval_remarks"]
	sites = frappe.get_list("UG Site", fields=fields, limit_page_length=0, order_by="modified desc")
	rows = []
	for site in sites:
		vendor = site.vendor_user == user
		if vendor and not site.splicer:
			# The vendor still has to pick a splicer for this site.
			rows.append({
				"site": site.name, "node_id": site.node_id, "node_name": site.node_name, "zone": site.zone,
				"work_type": site.work_type, "stage": site.current_stage, "kind": "Splicer", "person": None,
				"status": "To Assign", "assigned_on": None, "approved_on": None, "closed_on": None, "remarks": None,
				"splicing_status": site.splicing_status, "mine": False, "vendor": True,
			})
		for kind, a in ASSIGNMENTS.items():
			p = a["prefix"]
			status = site.get(f"{p}_approval_status")
			if not (site.get(a["field"]) and status):
				continue
			mine = site.get(a["user_field"]) == user
			# The vendor follows its splicers' assignments and re-assigns a rejected one.
			by_vendor = vendor and kind == "Splicer"
			if not (mine or by_vendor or (see_all and status in ("In Progress", "Closed"))):
				continue
			rows.append({
				"site": site.name,
				"node_id": site.node_id,
				"node_name": site.node_name,
				"zone": site.zone,
				"work_type": site.work_type,
				"stage": site.current_stage,
				"kind": kind,
				"person": site.get(a["field"]),
				"status": status,
				"assigned_on": site.get(f"{p}_request_date"),
				"approved_on": site.get(f"{p}_approved_on"),
				"closed_on": site.get(f"{p}_closed_on"),
				"remarks": site.get(f"{p}_approval_remarks"),
				"splicing_status": site.splicing_status if kind == "Splicer" else None,
				"mine": mine,
				"vendor": by_vendor,
			})
	# Pending / Rejected tabs: for whoever has own assignments, or is only an Area Manager / Splicer
	# (an Administrator holds every role but only follows approved work).
	has_own = any(row["mine"] or row["vendor"] for row in rows) or (
		not see_all and bool({"UG Area Manager", "UG Splicer", "UG Vendor"} & set(frappe.get_roles()))
	)
	return {"rows": rows, "see_all": see_all, "has_own": has_own}


@frappe.whitelist()
def resend_assignment_request(site, kind):
	"""Send the pending approval request again (Back Office / Admin)."""
	if kind not in ASSIGNMENTS:
		frappe.throw(_("Unknown assignment {0}.").format(kind))
	doc = frappe.get_doc("UG Site", site)
	doc.check_permission("write")
	if doc.get(f"{ASSIGNMENTS[kind]['prefix']}_approval_status") != "Pending":
		frappe.throw(_("There is no pending {0} approval on this site.").format(_(kind)))
	send_assignment_request(doc, kind)


@frappe.whitelist()
def assign_splicer(site, splicer):
	"""The site's splicing vendor (or anyone who may edit the site's team) assigns one of the
	vendor's splicers; the splicer then gets the approval request."""
	doc = frappe.get_doc("UG Site", site)
	if not doc.splicing_vendor:
		frappe.throw(_("Set the Splicing Vendor of the site first."))
	if frappe.session.user != doc.vendor_user and not doc.has_permlevel_access_to("splicer", permission_type="write"):
		frappe.throw(_("Only the splicing vendor {0} can assign the splicer.").format(doc.splicing_vendor),
		             frappe.PermissionError)
	vendor, active = frappe.db.get_value("UG Splicer", splicer, ["vendor", "is_active"]) or (None, 0)
	if vendor != doc.splicing_vendor or not active:
		frappe.throw(_("{0} is not an active splicer of {1}.").format(splicer, doc.splicing_vendor))
	doc.splicer = splicer
	doc.save(ignore_permissions=True)
	doc.add_comment("Comment", _("Splicer {0} assigned by {1}.").format(splicer, frappe.utils.get_fullname()))
	return doc.splicer_approval_status


def notify_splicing_vendor(site):
	"""Ask the splicing vendor to assign one of its splicers to the site."""
	from frappe.utils import get_url_to_form

	vendor = frappe.db.get_value("UG Vendor", site.splicing_vendor, ["vendor_name", "user", "email"], as_dict=True)
	if not vendor or not (vendor.user or vendor.email):
		frappe.msgprint(
			_("Splicing vendor {0} has no ERP user or email: tell them to assign a splicer.").format(site.splicing_vendor),
			indicator="orange",
			alert=True,
		)
		return
	label = " ".join(filter(None, [site.node_id, site.node_name])) or site.name
	url = get_url_to_form("UG Site", site.name)
	subject = _("Assign a splicer: site {0}").format(label)
	message = (
		f"<p>{_('Dear {0},').format(vendor.vendor_name)}</p>"
		f"<p>{_('Splicing of site {0} (area {1}) is given to you. Please assign one of your splicers.').format(label, site.zone or '-')}</p>"
		f'<p><a href="{url}">{_("Open the site")}</a> {_("and use Splicer → Assign Splicer, or the Assignments board.")}</p>'
	)
	if vendor.user:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": vendor.user,
				"type": "Alert",
				"document_type": "UG Site",
				"document_name": site.name,
				"subject": subject[:140],
				"email_content": message,
			}
		).insert(ignore_permissions=True)
	if vendor.email and cint(get_setting("send_emails")):
		frappe.sendmail(recipients=[vendor.email], subject=subject[:140], message=message,
		                reference_doctype="UG Site", reference_name=site.name)
	frappe.msgprint(_("Splicing vendor {0} asked to assign a splicer.").format(site.splicing_vendor), alert=True)


def pick_area_manager(zone):
	"""The active Area Manager of the area; with several, the one with the fewest active sites."""
	managers = frappe.get_all(
		"UG Employee",
		filters={"designation": "Area Manager", "is_active": 1, "zone": zone},
		pluck="name",
	)
	if len(managers) <= 1:
		return managers[0] if managers else None
	site = frappe.qb.DocType("UG Site")
	load = dict(
		frappe.qb.from_(site)
		.select(site.area_manager, Count("*"))
		.where(site.area_manager.isin(managers) & (site.final_ug_status == "Active"))
		.groupby(site.area_manager)
		.run()
	)
	return min(managers, key=lambda m: (load.get(m, 0), m))


@frappe.whitelist()
def read_kmz(file_url, site=None):
	"""Values for a new (unsaved) UG Site form from an attached KMZ / KML."""
	frappe.has_permission("UG Site", "create" if not site else "write", throw=True)
	return parse_kmz_file(file_url)


def parse_kmz_file(file_url):
	from underground.kmz_reader import parse_kmz

	file_doc = frappe.get_doc("File", {"file_url": file_url})
	file_name = file_doc.file_name or file_url
	if not file_name.lower().endswith((".kmz", ".kml")):
		frappe.throw(_("Attach the KMZ (or KML) file."))
	try:
		data = parse_kmz(file_doc.get_content(), file_name)
	except Exception:
		frappe.log_error(title="UG Site: could not read KMZ")
		frappe.throw(_("Could not read this KMZ. Is it the KMZ from Airtel, opened fine in Google Earth?"))
	if not data["latitude"] and not data["proposed_length"]:
		frappe.throw(_("No site point or route was found in this KMZ. Enter the KMZ details by hand."))
	return data


@frappe.whitelist()
def create_row_applications(site):
	"""Create a draft ROW Application for every authority on the site that has none yet."""
	frappe.has_permission("ROW Application", "create", throw=True)
	doc = frappe.get_doc("UG Site", site)
	doc.check_permission("read")
	created = []
	for row in doc.row_authorities:
		if frappe.db.exists("ROW Application", {"ug_site": site, "row_authority": row.row_authority}):
			continue
		application = frappe.get_doc(
			{
				"doctype": "ROW Application",
				"ug_site": site,
				"row_authority": row.row_authority,
				"authority_type": row.authority_type
				or frappe.db.get_value("ROW Authority", row.row_authority, "authority_type"),
				"chainage": row.chainage,
				"row_length_km": row.row_length_km,
			}
		).insert()
		created.append(application.name)
	refresh_site(site)
	return created


@frappe.whitelist()
def add_punch_points(site, lines, pp_category, responsible_party=None, ff1_status=None, pe_name=None):
	"""Turn Airtel's notepad list into Punch Point records, one per non-empty line."""
	frappe.has_permission("UG Punch Point", "create", throw=True)
	frappe.get_doc("UG Site", site).check_permission("read")
	responsible_party = responsible_party or frappe.db.get_value(
		"PP Category", pp_category, "default_responsible_party"
	)
	created = []
	for line in (lines or "").splitlines():
		issue = re.sub(r"^\s*(?:[-•*]|\d+[.)])\s*", "", line).strip()
		if not issue:
			continue
		pp = frappe.get_doc(
			{
				"doctype": "UG Punch Point",
				"ug_site": site,
				"pp_category": pp_category,
				"issue_description": issue,
				"responsible_party": responsible_party or "RKBG",
				"ff1_status": ff1_status,
				"pe_name": pe_name,
			}
		).insert()
		created.append(pp.name)
	return created
