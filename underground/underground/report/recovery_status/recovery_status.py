# Copyright (c) 2026, huda and contributors
"""Recovery Status — retention and SD / BG due and recovered, per invoiced site."""

import frappe
from frappe import _

from underground.utils import site_filters


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = site_filters(filters)
	data = frappe.get_list(
		"UG Site",
		filters=conditions,
		or_filters={"invoice_number": ("is", "set"), "sd_bg_outstanding": (">", 0)},
		fields=[c["fieldname"] for c in get_columns()],
		order_by="retention_due_date asc",
	)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "invoice_number", "label": _("Invoice No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "invoice_amount", "label": _("Invoice Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "retention_amount", "label": _("Retention"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "retention_due_date", "label": _("Retention Due"), "fieldtype": "Date", "width": 100},
		{"fieldname": "retention_recovery_status", "label": _("Retention Status"), "fieldtype": "Data", "width": 110},
		{"fieldname": "retention_recovery_date", "label": _("Recovered On"), "fieldtype": "Date", "width": 100},
		{"fieldname": "sd_bg_outstanding", "label": _("SD / BG Outstanding"), "fieldtype": "Currency", "width": 130},
		{"fieldname": "sd_bg_recovery_status", "label": _("SD / BG Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "sd_bg_recovery_date", "label": _("SD / BG Recovered On"), "fieldtype": "Date", "width": 120},
	]
