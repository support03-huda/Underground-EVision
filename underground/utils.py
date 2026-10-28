# Copyright (c) 2026, huda and contributors
"""Shared helpers for the UG Fiber ERP: settings, stage SLA and alert recipients."""

import frappe

SETTINGS_DEFAULTS = {
	"standard_trench_depth": 1.2,
	"kmz_due_day": 7,
	"feasibility_due_day": 21,
	"cwip_due_day": 25,
	"site_overdue_day": 150,
	"site_limit_day": 180,
	"airtel_reply_days": 5,
	"pp_ageing_alert_days": 15,
	"bg_expiry_alert_days": 30,
	"retention_percent": 10,
	"send_emails": 1,
}

# Roles that see every site. Anyone else (UG Project Manager, UG Area Manager, UG Splicer,
# UG Vendor) sees only the sites assigned to them: see SITE_USER_FIELDS.
ALL_SITE_ROLES = {
	"System Manager",
	"UG Admin",
	"UG Back Office",
	"UG Management",
	"UG Survey Team",
	"UG ROW Team",
	"UG Material Team",
	"UG Warehouse",
	"UG Execution Team",
	"UG ATC Manager",
	"UG Billing",
}

# Role -> the user field on a site (and its linked records) that assigns the site to that user.
SITE_USER_FIELDS = {
	"UG Project Manager": "pm_user",
	"UG Area Manager": "am_user",
	"UG Splicer": "splicer_user",
	"UG Vendor": "vendor_user",
}


def get_setting(fieldname):
	"""UG Settings value, falling back to the documented default when never set."""
	value = frappe.db.get_single_value("UG Settings", fieldname)
	if value in (None, "", 0) and fieldname in SETTINGS_DEFAULTS and fieldname != "send_emails":
		return SETTINGS_DEFAULTS[fieldname]
	if value is None:
		return SETTINGS_DEFAULTS.get(fieldname)
	return value


def get_stage_sla(stage):
	"""(end_day, owner_role) for a stage from the UG Stage SLA master, or (None, None)."""
	if not stage or not frappe.db.exists("UG Stage SLA", stage):
		return None, None
	sla = frappe.db.get_value("UG Stage SLA", stage, ["end_day", "owner_role"], as_dict=True)
	return sla.end_day, sla.owner_role


def get_role_users(*roles):
	"""Enabled users holding any of `roles`."""
	if not roles:
		return []
	has_role = frappe.qb.DocType("Has Role")
	user = frappe.qb.DocType("User")
	rows = (
		frappe.qb.from_(has_role)
		.join(user)
		.on(user.name == has_role.parent)
		.select(user.name)
		.distinct()
		.where(
			(has_role.parenttype == "User")
			& (has_role.role.isin(list(roles)))
			& (user.enabled == 1)
			& (user.name.notin(["Administrator", "Guest"]))
		)
		.run(pluck=True)
	)
	return rows


SITE_FILTER_FIELDS = ("zone", "district", "project_manager", "work_type", "current_stage")


def site_filters(filters):
	"""The common report filters (zone, district, PM, work type, stage) as UG Site filters."""
	return {field: filters.get(field) for field in SITE_FILTER_FIELDS if filters.get(field)}


def filtered_sites(filters):
	"""Names of the UG Sites matching the common report filters, or None when none is set."""
	conditions = site_filters(filters)
	if not conditions:
		return None
	return frappe.get_list("UG Site", filters=conditions, pluck="name")


def get_user_vendor(user=None):
	"""The UG Vendor whose login is `user`, if any."""
	return frappe.db.get_value("UG Vendor", {"user": user or frappe.session.user}, "name")


def sees_all_sites(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(ALL_SITE_ROLES & set(frappe.get_roles(user)))
