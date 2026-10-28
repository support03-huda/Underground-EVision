# Copyright (c) 2026, huda and contributors
"""Weekly Issue List — open issues per active site for the weekly call with senior management:
length extension, rate revision, ROW, CWIP, Job ID and punch points."""

import frappe
from frappe import _

from underground.utils import site_filters


def execute(filters=None):
	filters = frappe._dict(filters or {})
	conditions = {**site_filters(filters), "final_ug_status": "Active", "is_mobilization": 0}
	sites = frappe.get_list(
		"UG Site",
		filters=conditions,
		fields=[
			"name",
			"node_id",
			"node_name",
			"project_manager",
			"current_stage",
			"site_ageing",
			"site_feasibility",
			"length_extension_status",
			"rate_revision_status",
			"row_overall_status",
			"cwip_id",
			"cwip_mapping_status",
			"job_id",
			"job_id_mapping_status",
			"job_id_approval_status",
			"open_pp",
			"current_blocker",
			"next_action",
		],
		order_by="site_ageing desc",
	)
	data = []
	for site in sites:
		issues = get_issues(site)
		if issues:
			data.append({**site, "issues": "; ".join(issues), "issue_count": len(issues)})
	return get_columns(), data


def get_issues(site):
	issues = []
	if site.length_extension_status == "Requested":
		issues.append(_("Length extension awaiting Airtel"))
	if site.rate_revision_status == "Requested":
		issues.append(_("Rate revision awaiting Airtel"))
	if site.row_overall_status in ("Pending", "Rejected"):
		issues.append(_("ROW {0}").format(site.row_overall_status.lower()))
	if site.site_feasibility == "Feasible":
		if not site.cwip_id:
			issues.append(_("CWIP ID missing"))
		elif site.cwip_mapping_status in ("Incorrect", "Follow-up"):
			issues.append(_("CWIP mapping {0}").format(site.cwip_mapping_status.lower()))
		if site.job_id and site.job_id_mapping_status == "Incorrect":
			issues.append(_("Job ID mapping incorrect"))
		elif site.job_id and site.job_id_approval_status != "Approved":
			issues.append(_("Job ID approval pending"))
	if site.open_pp:
		issues.append(_("{0} open punch points").format(site.open_pp))
	if site.current_blocker:
		issues.append(site.current_blocker)
	return issues


def get_columns():
	return [
		{"fieldname": "name", "label": _("Site"), "fieldtype": "Link", "options": "UG Site", "width": 130},
		{"fieldname": "node_id", "label": _("Node ID"), "fieldtype": "Data", "width": 100},
		{"fieldname": "node_name", "label": _("Node Name"), "fieldtype": "Data", "width": 150},
		{"fieldname": "project_manager", "label": _("Project Manager"), "fieldtype": "Link", "options": "UG Employee", "width": 140},
		{"fieldname": "current_stage", "label": _("Stage"), "fieldtype": "Data", "width": 180},
		{"fieldname": "site_ageing", "label": _("Ageing (days)"), "fieldtype": "Int", "width": 80},
		{"fieldname": "issue_count", "label": _("Issues"), "fieldtype": "Int", "width": 60},
		{"fieldname": "issues", "label": _("Open Issues"), "fieldtype": "Data", "width": 400},
		{"fieldname": "next_action", "label": _("Next Action"), "fieldtype": "Data", "width": 200},
	]
