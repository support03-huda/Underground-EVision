# Copyright (c) 2026, huda and contributors
"""Record-level access: a Project Manager, Area Manager, Splicer or Vendor sees only the sites
assigned to them (and those sites' ROW Applications, Daily Progress, Punch Points and Material
Requests, where the record carries their user field). Every other UG role sees all sites.
A vendor also sees only its own splicers."""

import frappe

from underground.utils import SITE_USER_FIELDS, get_user_vendor, sees_all_sites


def user_fields(doctype, user):
	"""The site-assignment fields of `doctype` that apply to the user's roles."""
	roles = set(frappe.get_roles(user))
	meta = frappe.get_meta(doctype)
	return [field for role, field in SITE_USER_FIELDS.items() if role in roles and meta.has_field(field)]


def get_conditions(doctype, user=None):
	user = user or frappe.session.user
	if sees_all_sites(user):
		return ""
	fields = user_fields(doctype, user) or ["pm_user"]
	user = frappe.db.escape(user)
	return "(" + " or ".join(f"`tab{doctype}`.`{field}` = {user}" for field in fields) + ")"


def has_site_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if sees_all_sites(user) or doc.is_new():
		return True
	return any(doc.get(field) == user for field in user_fields(doc.doctype, user) or ["pm_user"])


def has_app_permission():
	"""Show the Underground app icon only to System Managers and users with a UG role."""
	from underground.install import ROLES

	roles = set(frappe.get_roles())
	return "System Manager" in roles or bool(roles & set(ROLES))


def ug_site_conditions(user=None, doctype=None):
	return get_conditions("UG Site", user)


def row_application_conditions(user=None, doctype=None):
	return get_conditions("ROW Application", user)


def daily_progress_conditions(user=None, doctype=None):
	return get_conditions("UG Daily Progress", user)


def punch_point_conditions(user=None, doctype=None):
	return get_conditions("UG Punch Point", user)


def material_request_conditions(user=None, doctype=None):
	return get_conditions("UG Material Request", user)


def vendor_only(user):
	"""The vendor of a user who logs in as a UG Vendor and sees no more than its own sites."""
	user = user or frappe.session.user
	if sees_all_sites(user) or "UG Vendor" not in frappe.get_roles(user):
		return None
	return get_user_vendor(user) or ""


def splicer_conditions(user=None, doctype=None):
	vendor = vendor_only(user)
	if vendor is None:
		return ""
	return f"`tabUG Splicer`.`vendor` = {frappe.db.escape(vendor)}"


def has_splicer_permission(doc, ptype=None, user=None, debug=False):
	vendor = vendor_only(user)
	return vendor is None or doc.is_new() or doc.vendor == vendor
