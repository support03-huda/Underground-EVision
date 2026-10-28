# Copyright (c) 2026, huda and contributors
"""Site Tracker — one row per site: stage, ageing, key Airtel IDs, blocker and next action."""

import frappe
from frappe import _

from underground.utils import site_filters


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = site_filters(filters)
	if filters.final_ug_status:
		conditions["final_ug_status"] = filters.final_ug_status
	data = frappe.get_list(
		"UG Site",
		filters=conditions,
		fields=[field["fieldname"] for field in COLUMNS],
		order_by="site_ageing desc",
	)
	return [{**c, "label": _(c["label"])} for c in COLUMNS], data


def col(fieldname, label, fieldtype="Data", width=110, options=None):
	return {"fieldname": fieldname, "label": label, "fieldtype": fieldtype, "width": width, "options": options}


COLUMNS = [
	col("name", "Site", "Link", 130, "UG Site"),
	col("node_id", "Node ID"),
	col("node_name", "Node Name", width=150),
	col("work_type", "Work Type", width=90),
	col("zone", "Zone"),
	col("district", "District"),
	col("project_manager", "Project Manager", "Link", 140, "UG Employee"),
	col("po_number", "PO Number"),
	col("po_amount", "PO Amount", "Currency"),
	col("current_stage", "Stage", width=190),
	col("site_ageing", "Ageing (days)", "Int", 90),
	col("stage_overdue", "Stage Overdue", "Check", 80),
	col("cwip_id", "CWIP ID"),
	col("job_id", "Job ID"),
	col("vlc_code", "VLC Code"),
	col("row_overall_status", "ROW Status"),
	col("td_scope_km", "T&D Scope (km)", "Float", 90),
	col("td_cumulative_km", "T&D Done (km)", "Float", 90),
	col("cable_blowing_cumulative_km", "Blowing (km)", "Float", 90),
	col("open_pp", "Open PP", "Int", 70),
	col("billing_ready", "Billing Ready", "Check", 80),
	col("current_blocker", "Current Blocker", width=200),
	col("next_action", "Next Action", width=200),
]
