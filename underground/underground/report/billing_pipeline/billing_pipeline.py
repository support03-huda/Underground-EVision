# Copyright (c) 2026, huda and contributors
"""Billing Pipeline — billing-ready, invoiced and paid sites with amounts."""

import frappe
from frappe import _

from underground.utils import site_filters


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = site_filters(filters)
	if filters.billing_status:
		conditions["billing_status"] = filters.billing_status
	data = frappe.get_list(
		"UG Site",
		filters=conditions,
		or_filters={"billing_ready": 1, "billing_status": ("!=", "Pending"), "is_mobilization": 1},
		fields=[c["fieldname"] for c in get_columns()],
		order_by="billing_status asc, invoice_date desc",
	)
	return get_columns(), data


def get_columns():
	return [
		{"fieldname": "name", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "node_name", "label": _("Node Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "work_type", "label": _("Work Type"), "fieldtype": "Data", "width": 90},
		{"fieldname": "po_number", "label": _("PO Number"), "fieldtype": "Data", "width": 120},
		{"fieldname": "po_amount", "label": _("PO Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "mo_po_amount", "label": _("MO PO Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "billing_ready", "label": _("Billing Ready"), "fieldtype": "Check", "width": 80},
		{"fieldname": "billing_status", "label": _("Billing Status"), "fieldtype": "Data", "width": 100},
		{"fieldname": "invoice_number", "label": _("Invoice No"), "fieldtype": "Data", "width": 120},
		{"fieldname": "invoice_date", "label": _("Invoice Date"), "fieldtype": "Date", "width": 100},
		{"fieldname": "invoice_amount", "label": _("Invoice Amount"), "fieldtype": "Currency", "width": 120},
		{"fieldname": "retention_amount", "label": _("Retention"), "fieldtype": "Currency", "width": 110},
		{"fieldname": "handover_status", "label": _("Handover"), "fieldtype": "Data", "width": 100},
	]
