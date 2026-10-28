# Copyright (c) 2026, huda and contributors
"""SLA Breach — active sites past their current stage's day window (UG Stage SLA)."""

import frappe
from frappe import _
from frappe.utils import cint

from underground.utils import site_filters


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {**site_filters(filters), "final_ug_status": "Active", "stage_overdue": 1}
	data = frappe.get_list(
		"UG Site",
		filters=conditions,
		fields=[
			"name",
			"node_id",
			"node_name",
			"project_manager",
			"current_stage",
			"stage_sla_end_day",
			"site_ageing",
			"current_blocker",
			"next_action",
		],
		order_by="site_ageing desc",
	)
	for row in data:
		row.days_over = cint(row.site_ageing) - cint(row.stage_sla_end_day)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "node_name", "label": _("Node Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "project_manager", "label": _("Project Manager"), "fieldtype": "Link", "options": "UG Employee", "width": 140},
		{"fieldname": "current_stage", "label": _("Stage"), "fieldtype": "Data", "width": 190},
		{"fieldname": "stage_sla_end_day", "label": _("SLA End Day"), "fieldtype": "Int", "width": 90},
		{"fieldname": "site_ageing", "label": _("Ageing (days)"), "fieldtype": "Int", "width": 90},
		{"fieldname": "days_over", "label": _("Days Over"), "fieldtype": "Int", "width": 80},
		{"fieldname": "current_blocker", "label": _("Current Blocker"), "fieldtype": "Data", "width": 200},
		{"fieldname": "next_action", "label": _("Next Action"), "fieldtype": "Data", "width": 200},
	]
