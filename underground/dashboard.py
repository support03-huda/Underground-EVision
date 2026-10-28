# Copyright (c) 2026, huda and contributors
"""Data for the UG Dashboard page (underground/page/ug_dashboard): KPI cards, money, site map,
stage and ageing charts, area table, weekly progress and the "needs attention" lists. Everything
goes through the user's permissions, so a Project Manager or Area Manager sees only their sites."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, get_first_day_of_week, getdate, today

from underground.utils import get_setting

SITE_FIELDS = [
	"name", "node_id", "node_name", "zone", "work_type", "current_stage", "final_ug_status", "site_ageing",
	"stage_overdue", "po_amount", "billing_ready", "billing_status", "invoice_amount", "retention_amount",
	"retention_recovery_status", "sd_bg_outstanding", "open_pp", "row_overall_status", "kmz_latitude",
	"kmz_longitude", "survey_latitude", "survey_longitude", "project_manager", "area_manager",
	"td_cumulative_km", "td_scope_km", "is_mobilization", "material_dispatched", "execution_release_date",
]
FILTERS = ("zone", "work_type", "project_manager", "area_manager")
BILLED = ("Submitted", "Approved", "Paid")
AGEING_BUCKETS = [(0, 30, "0-30"), (31, 90, "31-90"), (91, 120, "91-120"), (121, 150, "121-150"),
                  (151, 180, "151-180"), (181, 100000, "180+")]
WEEKS = 12


@frappe.whitelist()
def get_data(zone=None, work_type=None, project_manager=None, area_manager=None):
	values = {"zone": zone, "work_type": work_type, "project_manager": project_manager, "area_manager": area_manager}
	filters = {k: v for k, v in values.items() if v}
	sites = frappe.get_list("UG Site", fields=SITE_FIELDS, filters=filters, limit_page_length=0)
	names = [s.name for s in sites]
	active = [s for s in sites if s.final_ug_status == "Active"]
	overdue_day = cint(get_setting("site_overdue_day")) or 150
	limit_day = cint(get_setting("site_limit_day")) or 180

	return {
		"kpis": kpis(sites, active, overdue_day, limit_day),
		"money": money(sites),
		"stages": stage_counts(active),
		"ageing": ageing(active, overdue_day, limit_day),
		"work_types": count_by(active, "work_type"),
		"areas": area_table(sites, overdue_day),
		"map": map_points(sites, overdue_day),
		"progress": weekly_progress(names),
		"attention": attention(active, names, overdue_day),
		"filters": filters,
		"limit_day": limit_day,
	}


def kpis(sites, active, overdue_day, limit_day):
	return {
		"total": len(sites),
		"active": len(active),
		"completed": sum(1 for s in sites if s.final_ug_status == "Completed"),
		"in_execution": sum(1 for s in active if s.execution_release_date),
		"stage_overdue": sum(1 for s in active if s.stage_overdue),
		"past_overdue": sum(1 for s in active if cint(s.site_ageing) > overdue_day),
		"past_limit": sum(1 for s in active if cint(s.site_ageing) > limit_day),
		"row_pending": sum(1 for s in active if s.row_overall_status in ("Pending", "Rejected")),
		"open_pp": sum(cint(s.open_pp) for s in active),
		"billing_ready": sum(1 for s in sites if s.billing_ready and s.billing_status not in BILLED),
		"td_done_km": flt(sum(flt(s.td_cumulative_km) for s in sites), 2),
		"td_scope_km": flt(sum(flt(s.td_scope_km) for s in sites), 2),
		"avg_ageing": round(sum(cint(s.site_ageing) for s in active) / len(active)) if active else 0,
	}


def money(sites):
	billed = [s for s in sites if s.billing_status in BILLED]
	return {
		"po_value": sum(flt(s.po_amount) for s in sites),
		"billed": sum(flt(s.invoice_amount) for s in billed),
		"paid": sum(flt(s.invoice_amount) for s in sites if s.billing_status == "Paid"),
		"ready_not_billed": sum(flt(s.po_amount) for s in sites if s.billing_ready and s.billing_status not in BILLED),
		"retention_pending": sum(flt(s.retention_amount) for s in sites if s.retention_recovery_status != "Recovered"),
		"sd_bg_outstanding": sum(flt(s.sd_bg_outstanding) for s in sites),
	}


def stage_counts(active):
	from underground.underground.doctype.ug_site.ug_site import STAGES

	counts = {stage: 0 for stage in STAGES}
	overdue = {stage: 0 for stage in STAGES}
	for s in active:
		if s.current_stage in counts:
			counts[s.current_stage] += 1
			overdue[s.current_stage] += 1 if s.stage_overdue else 0
	return {"labels": list(counts), "on_time": [counts[k] - overdue[k] for k in counts],
	        "overdue": [overdue[k] for k in counts]}


def ageing(active, overdue_day, limit_day):
	counts = [0] * len(AGEING_BUCKETS)
	for s in active:
		days = cint(s.site_ageing)
		for i, (low, high, _label) in enumerate(AGEING_BUCKETS):
			if low <= days <= high:
				counts[i] += 1
				break
	return {"labels": [b[2] for b in AGEING_BUCKETS], "values": counts}


def count_by(rows, field):
	counts = {}
	for row in rows:
		key = row.get(field) or _("Not set")
		counts[key] = counts.get(key, 0) + 1
	ordered = sorted(counts.items(), key=lambda kv: -kv[1])
	return {"labels": [k for k, _v in ordered], "values": [v for _k, v in ordered]}


def area_table(sites, overdue_day):
	areas = {}
	for s in sites:
		a = areas.setdefault(s.zone or _("Not set"), {
			"zone": s.zone or _("Not set"), "active": 0, "completed": 0, "row_pending": 0, "open_pp": 0,
			"overdue": 0, "billing_ready": 0, "po_value": 0, "billed": 0, "ageing": 0,
		})
		a["po_value"] += flt(s.po_amount)
		if s.billing_status in BILLED:
			a["billed"] += flt(s.invoice_amount)
		if s.billing_ready and s.billing_status not in BILLED:
			a["billing_ready"] += 1
		if s.final_ug_status == "Completed":
			a["completed"] += 1
		if s.final_ug_status != "Active":
			continue
		a["active"] += 1
		a["ageing"] += cint(s.site_ageing)
		a["row_pending"] += 1 if s.row_overall_status in ("Pending", "Rejected") else 0
		a["open_pp"] += cint(s.open_pp)
		a["overdue"] += 1 if (s.stage_overdue or cint(s.site_ageing) > overdue_day) else 0
	rows = sorted(areas.values(), key=lambda a: (-a["active"], a["zone"]))
	for a in rows:
		a["avg_ageing"] = round(a.pop("ageing") / a["active"]) if a["active"] else 0
	return rows


def health(site, overdue_day):
	"""done / late / watch / on_track — the colour of the site on the map."""
	if site.final_ug_status != "Active":
		return "done"
	if cint(site.site_ageing) > overdue_day:
		return "late"
	if site.stage_overdue:
		return "watch"
	return "on_track"


def map_points(sites, overdue_day):
	points = []
	for s in sites:
		lat = flt(s.survey_latitude) or flt(s.kmz_latitude)
		lon = flt(s.survey_longitude) or flt(s.kmz_longitude)
		if not (lat and lon):
			continue
		points.append({
			"name": s.name, "node_id": s.node_id or s.name, "node_name": s.node_name, "lat": lat, "lon": lon,
			"zone": s.zone, "stage": s.current_stage, "ageing": cint(s.site_ageing), "work_type": s.work_type,
			"health": health(s, overdue_day),
		})
	return {"points": points, "without_location": len(sites) - len(points)}


def weekly_progress(names):
	"""T&D and cable blowing (km) per week for the last WEEKS weeks, from Daily Progress."""
	start = get_first_day_of_week(add_days(today(), -7 * (WEEKS - 1)))
	weeks = [add_days(start, 7 * i) for i in range(WEEKS)]
	td, blowing = [0.0] * WEEKS, [0.0] * WEEKS
	if names:
		rows = frappe.get_list(
			"UG Daily Progress",
			fields=["progress_date", "td_km", "cable_blowing_km"],
			filters={"ug_site": ["in", names], "progress_date": [">=", start]},
			limit_page_length=0,
		)
		for row in rows:
			index = (getdate(row.progress_date) - getdate(start)).days // 7
			if 0 <= index < WEEKS:
				td[index] += flt(row.td_km)
				blowing[index] += flt(row.cable_blowing_km)
	return {
		"labels": [getdate(w).strftime("%d %b") for w in weeks],
		"td": [flt(v, 3) for v in td],
		"blowing": [flt(v, 3) for v in blowing],
	}


def attention(active, names, overdue_day):
	"""What needs someone today, each list short and linked."""
	user = frappe.session.user
	day = today()
	result = {}

	result["late_sites"] = [
		{"name": s.name, "label": s.node_id or s.name, "detail": f"{s.current_stage or ''}", "days": cint(s.site_ageing),
		 "zone": s.zone}
		for s in sorted(active, key=lambda s: -cint(s.site_ageing))[:8]
		if cint(s.site_ageing) > 0
	]

	from underground.underground.doctype.ug_site.ug_site import get_assignments

	board = get_assignments()
	result["my_approvals"] = [
		{"name": r["site"], "label": r["node_id"] or r["site"], "detail": _(r["kind"]), "status": r["status"]}
		for r in board["rows"]
		if (r["mine"] and r["status"] == "Pending") or (r.get("vendor") and r["status"] in ("To Assign", "Rejected"))
	][:8]

	if names:
		result["row_followups"] = [
			{"name": r.name, "label": r.node_id or r.ug_site, "detail": r.row_authority, "date": str(r.next_followup_date),
			 "overdue": getdate(r.next_followup_date) < getdate(day)}
			for r in frappe.get_list(
				"ROW Application",
				fields=["name", "ug_site", "node_id", "row_authority", "next_followup_date"],
				filters={"ug_site": ["in", names], "permission_status": ["!=", "Received"],
				         "next_followup_date": ["<=", add_days(day, 2)]},
				order_by="next_followup_date asc",
				limit_page_length=8,
			)
		]
		result["row_breached"] = frappe.db.count(
			"ROW Application", {"ug_site": ["in", names], "sla_breached": 1, "permission_status": ["!=", "Received"]}
		) if frappe.has_permission("ROW Application", "read") else 0
		alert_days = cint(get_setting("bg_expiry_alert_days")) or 30
		result["bg_expiring"] = [
			{"name": r.name, "label": r.node_id or r.ug_site, "detail": r.row_authority, "date": str(r.bg_end_date)}
			for r in frappe.get_list(
				"ROW Application",
				fields=["name", "ug_site", "node_id", "row_authority", "bg_end_date"],
				filters={"ug_site": ["in", names], "bg_required": 1, "bg_released_date": ["is", "not set"],
				         "bg_end_date": ["between", [add_days(day, -365), add_days(day, alert_days)]]},
				order_by="bg_end_date asc",
				limit_page_length=8,
			)
		]
		result["material_requests"] = [
			{"name": r.name, "label": r.node_id or r.ug_site, "detail": r.status, "date": str(r.requested_on or "")}
			for r in frappe.get_list(
				"UG Material Request",
				fields=["name", "ug_site", "node_id", "status", "requested_on"],
				filters={"ug_site": ["in", names], "status": "Requested"},
				order_by="requested_on asc",
				limit_page_length=8,
			)
		] if frappe.db.exists("DocType", "UG Material Request") else []
	return result
