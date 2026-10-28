# Copyright (c) 2026, huda and contributors
"""ROW Tracker — one row per authority: status, ageing, amounts, BG expiry and follow-up date."""

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
	for field in ("authority_type", "permission_status"):
		if filters.get(field):
			conditions[field] = filters.get(field)
	if filters.sla_breached:
		conditions["sla_breached"] = 1
	data = frappe.get_list(
		"ROW Application",
		filters=conditions,
		fields=[c["fieldname"] for c in get_columns()],
		order_by="row_ageing desc",
	)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("ROW Application"), "fieldtype": "Link", "options": "ROW Application", "width": 130},
		{"fieldname": "ug_site", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "row_authority", "label": _("Authority"), "fieldtype": "Link", "options": "ROW Authority", "width": 160},
		{"fieldname": "authority_type", "label": _("Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "row_length_km", "label": _("Length (km)"), "fieldtype": "Float", "width": 80},
		{"fieldname": "application_no", "label": _("Application No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "application_date", "label": _("Applied On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "permission_status", "label": _("Permission"), "fieldtype": "Data", "width": 90},
		{"fieldname": "permission_date", "label": _("Permission Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "row_ageing", "label": _("Ageing (days)"), "fieldtype": "Int", "width": 80},
		{"fieldname": "expected_days", "label": _("Expected"), "fieldtype": "Int", "width": 70},
		{"fieldname": "sla_breached", "label": _("SLA Breached"), "fieldtype": "Check", "width": 80},
		{"fieldname": "demand_note_amount", "label": _("Demand Note"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "payment_amount", "label": _("Paid"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "sd_amount", "label": _("SD Amount"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "sd_status", "label": _("SD Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "bg_amount", "label": _("BG Amount"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "bg_end_date", "label": _("BG Expiry"), "fieldtype": "Date", "width": 100},
		{"fieldname": "bg_status", "label": _("BG Status"), "fieldtype": "Data", "width": 90},
		{"fieldname": "current_blocker", "label": _("Current Blocker"), "fieldtype": "Data", "width": 180},
		{"fieldname": "next_followup_date", "label": _("Next Follow-up"), "fieldtype": "Date", "width": 100},
		{"fieldname": "responsible_person", "label": _("Responsible"), "fieldtype": "Link", "options": "User", "width": 140},
	]
