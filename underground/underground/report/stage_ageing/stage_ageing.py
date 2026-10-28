# Copyright (c) 2026, huda and contributors
"""Stage Ageing — count of active sites per stage by ageing bucket."""

import frappe
from frappe import _
from frappe.utils import cint

from underground.underground.doctype.ug_site.ug_site import STAGES
from underground.utils import site_filters

BUCKETS = [("b0_30", "0-30", 0, 30), ("b31_60", "31-60", 31, 60), ("b61_90", "61-90", 61, 90), ("b90", "90+", 91, None)]


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {**site_filters(filters), "final_ug_status": "Active"}
	sites = frappe.get_list("UG Site", filters=conditions, fields=["current_stage", "site_ageing"])
	data = []
	for stage in STAGES:
		row = {"stage": stage, "total": 0}
		for key, _label, low, high in BUCKETS:
			row[key] = sum(
				1
				for s in sites
				if s.current_stage == stage and cint(s.site_ageing) >= low and (high is None or cint(s.site_ageing) <= high)
			)
			row["total"] += row[key]
		data.append(row)
	chart = {
		"data": {
			"labels": [s.split(" - ", 1)[-1] for s in STAGES],
			"datasets": [{"name": label, "values": [r[key] for r in data]} for key, label, _l, _h in BUCKETS],
		},
		"type": "bar",
		"barOptions": {"stacked": 1},
	}
	return get_columns(), data, None, chart


def get_columns():
	columns = [{"fieldname": "stage", "label": _("Stage"), "fieldtype": "Data", "width": 220}]
	columns += [{"fieldname": key, "label": _("{0} days").format(label), "fieldtype": "Int", "width": 100} for key, label, _l, _h in BUCKETS]
	columns.append({"fieldname": "total", "label": _("Total"), "fieldtype": "Int", "width": 90})
	return columns
