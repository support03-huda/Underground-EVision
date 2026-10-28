# Copyright (c) 2026, huda and contributors
"""ATC Tracker — one row per punch point, grouped by Airtel vs RKBG responsibility."""

import frappe
from frappe import _

from underground.utils import filtered_sites


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	sites = filtered_sites(filters)
	if sites is not None:
		if not sites:
			return get_columns(), []
		conditions["ug_site"] = ("in", sites)
	if filters.ug_site:
		conditions["ug_site"] = filters.ug_site
	if filters.status == "Not Closed":
		conditions["status"] = ("!=", "Closed")
	elif filters.status:
		conditions["status"] = filters.status
	for field in ("responsible_party", "pp_category"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	rows = frappe.get_list(
		"UG Punch Point",
		filters=conditions,
		fields=[c["fieldname"] for c in get_columns() if c["fieldname"] != "indent"],
		order_by="responsible_party asc, current_ageing desc",
	)
	data = []
	for party in ("Airtel", "RKBG"):
		group = [r for r in rows if r.responsible_party == party]
		if not group:
			continue
		data.append({"name": _("{0} ({1})").format(party, len(group)), "indent": 0, "is_group": 1})
		data += [{**r, "indent": 1} for r in group]
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("Punch Point"), "fieldtype": "Data", "width": 150},
		{"fieldname": "ug_site", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "job_id", "label": _("Job ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "pp_category", "label": _("Category"), "fieldtype": "Data", "width": 120},
		{"fieldname": "sub_category", "label": _("Sub-Category"), "fieldtype": "Data", "width": 130},
		{"fieldname": "issue_description", "label": _("Issue"), "fieldtype": "Data", "width": 250},
		{"fieldname": "action_required", "label": _("Action Required"), "fieldtype": "Data", "width": 180},
		{"fieldname": "action_taken", "label": _("Action Taken"), "fieldtype": "Data", "width": 180},
		{"fieldname": "responsible_party", "label": _("Party"), "fieldtype": "Data", "width": 70},
		{"fieldname": "responsible_person", "label": _("Responsible"), "fieldtype": "Link", "options": "User", "width": 140},
		{"fieldname": "date_assigned", "label": _("Assigned"), "fieldtype": "Date", "width": 100},
		{"fieldname": "nc_resolved_date", "label": _("Resolved"), "fieldtype": "Date", "width": 100},
		{"fieldname": "current_ageing", "label": _("Ageing (days)"), "fieldtype": "Int", "width": 80},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 90},
	]
