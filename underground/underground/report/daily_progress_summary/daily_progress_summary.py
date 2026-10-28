# Copyright (c) 2026, huda and contributors
"""Daily Progress Summary — T&D and cable blowing km by day, site and vendor."""

import frappe
from frappe import _

from underground.utils import filtered_sites


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {}
	if filters.from_date and filters.to_date:
		conditions["progress_date"] = ("between", [filters.from_date, filters.to_date])
	sites = filtered_sites(filters)
	if sites is not None:
		if not sites:
			return get_columns(), []
		conditions["ug_site"] = ("in", sites)
	for field in ("ug_site", "vendor"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	data = frappe.get_list(
		"UG Daily Progress",
		filters=conditions,
		fields=[c["fieldname"] for c in get_columns()],
		order_by="progress_date desc, ug_site asc",
	)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "progress_date", "label": _("Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "ug_site", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "node_name", "label": _("Node Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "vendor", "label": _("Vendor / Team"), "fieldtype": "Link", "options": "UG Vendor", "width": 150},
		{"fieldname": "td_km", "label": _("T&D (km)"), "fieldtype": "Float", "width": 90},
		{"fieldname": "cable_blowing_km", "label": _("Cable Blowing (km)"), "fieldtype": "Float", "width": 120},
		{"fieldname": "ibd_m", "label": _("IBD / FTTB (m)"), "fieldtype": "Float", "width": 100},
		{"fieldname": "section_chainage", "label": _("Section / Chainage"), "fieldtype": "Data", "width": 140},
		{"fieldname": "remarks", "label": _("Remarks"), "fieldtype": "Data", "width": 200},
		{"fieldname": "name", "label": _("DPR"), "fieldtype": "Link", "options": "UG Daily Progress", "width": 130},
	]
