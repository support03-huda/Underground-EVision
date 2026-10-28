# Copyright (c) 2026, huda and contributors
"""Nightly job: recalculate ageing (it changes every day without anyone saving) and send the
UG alerts — one digest per person by email plus an in-app notification."""

from collections import defaultdict

import frappe
from frappe.utils import add_days, cint, date_diff, get_url_to_form, getdate, today

from underground.underground.doctype.row_application.row_application import refresh_ageing
from underground.underground.doctype.ug_site.ug_site import refresh_site
from underground.utils import get_role_users, get_setting, get_stage_sla

# Days an Area Manager / Splicer approval may stay pending before the daily reminder.
APPROVAL_DUE_DAYS = 2


def daily():
	refresh_open_records()
	frappe.db.commit()
	digest = Digest()
	site_alerts(digest)
	row_alerts(digest)
	punch_point_alerts(digest)
	digest.send()


def refresh_open_records():
	for site in frappe.get_all("UG Site", filters={"final_ug_status": "Active"}, pluck="name"):
		refresh_site(site)
	row_names = set(frappe.get_all("ROW Application", filters={"permission_status": ("!=", "Received")}, pluck="name"))
	row_names |= set(
		frappe.get_all("ROW Application", filters={"bg_required": 1, "bg_released_date": ("is", "not set")}, pluck="name")
	)
	for name in row_names:
		refresh_ageing(name)
	for pp in frappe.get_all("UG Punch Point", filters={"status": ("!=", "Closed")}, fields=["name", "date_assigned"]):
		if pp.date_assigned:
			frappe.db.set_value(
				"UG Punch Point", pp.name, "current_ageing", date_diff(today(), pp.date_assigned), update_modified=False
			)


class Digest:
	"""Collects alert lines per recipient (a user, or a plain email for Airtel contacts)."""

	def __init__(self):
		self.items = defaultdict(lambda: defaultdict(list))

	def add(self, recipients, alert, line):
		for recipient in recipients:
			if recipient:
				self.items[recipient][alert].append(line)

	def send(self):
		send_emails = cint(get_setting("send_emails"))
		for recipient, alerts in self.items.items():
			body = "".join(
				f"<h4>{alert} ({len(lines)})</h4><ul>{''.join(f'<li>{line}</li>' for line in lines)}</ul>"
				for alert, lines in alerts.items()
			)
			subject = "UG alerts: " + ", ".join(f"{alert} ({len(lines)})" for alert, lines in alerts.items())
			email = recipient
			if frappe.db.exists("User", recipient):
				email = frappe.db.get_value("User", recipient, "email")
				frappe.get_doc(
					{
						"doctype": "Notification Log",
						"for_user": recipient,
						"type": "Alert",
						"subject": subject[:140],
						"email_content": body,
					}
				).insert(ignore_permissions=True)
			if send_emails and email:
				frappe.sendmail(recipients=[email], subject=subject[:140], message=body)


def site_link(site):
	label = " ".join(filter(None, [site.name, site.node_id, site.node_name]))
	return f'<a href="{get_url_to_form("UG Site", site.name)}">{label}</a>'


def site_alerts(digest):
	back_office = get_role_users("UG Back Office")
	management = get_role_users("UG Management")
	kmz_due = cint(get_setting("kmz_due_day"))
	feasibility_due = cint(get_setting("feasibility_due_day"))
	cwip_due = cint(get_setting("cwip_due_day"))
	overdue_day = cint(get_setting("site_overdue_day"))
	limit_day = cint(get_setting("site_limit_day"))
	sites = frappe.get_all(
		"UG Site",
		filters={"final_ug_status": "Active", "is_mobilization": 0},
		fields=[
			"name",
			"node_id",
			"node_name",
			"pm_user",
			"am_user",
			"splicer_user",
			"am_approval_status",
			"am_request_date",
			"splicer_approval_status",
			"splicer_request_date",
			"airtel_spoc",
			"site_ageing",
			"kmz_overdue",
			"site_feasibility",
			"airtel_works_upload_status",
			"cwip_id",
			"current_stage",
			"stage_overdue",
			"stage_sla_end_day",
			"alert_150_sent",
			"alert_180_sent",
			"length_extension_status",
			"length_extension_request_date",
			"le_last_reminder",
			"rate_revision_status",
			"rate_revision_request_date",
			"rr_last_reminder",
		],
	)
	for site in sites:
		link, ageing = site_link(site), cint(site.site_ageing)
		spoc_email = frappe.db.get_value("Airtel SPOC", site.airtel_spoc, "email") if site.airtel_spoc else None

		for kind, prefix, user in (("Area Manager", "am", site.am_user), ("Splicer", "splicer", site.splicer_user)):
			requested = site.get(f"{prefix}_request_date")
			if site.get(f"{prefix}_approval_status") == "Pending" and requested and date_diff(today(), requested) >= APPROVAL_DUE_DAYS:
				digest.add(
					[user, *back_office],
					f"{kind} approval pending",
					f"{link}: waiting since {requested}",
				)
		if site.kmz_overdue:
			digest.add([*back_office, spoc_email], "KMZ overdue", f"{link}: no KMZ on day {ageing} (due by day {kmz_due})")
		if ageing > feasibility_due and not site.site_feasibility:
			digest.add([site.pm_user], "Feasibility overdue", f"{link}: no feasibility decision on day {ageing}")
		if (
			ageing > feasibility_due
			and site.site_feasibility == "Feasible"
			and site.airtel_works_upload_status in (None, "", "Pending", "Rework")
		):
			digest.add(
				[site.pm_user, *back_office],
				"SLD upload overdue",
				f"{link}: SLD / photos not accepted on Airtel Works by day {ageing}",
			)
		if ageing > cwip_due and not site.cwip_id and site.site_feasibility != "Not Feasible":
			digest.add(back_office, "CWIP missing", f"{link}: no CWIP ID on day {ageing}")
		if site.stage_overdue:
			_end, owner_role = get_stage_sla(site.current_stage)
			owners = get_role_users(owner_role) if owner_role else []
			digest.add(
				[site.pm_user, site.am_user, *owners],
				"Stage overdue",
				f"{link}: {site.current_stage}, day {ageing} (SLA ends day {site.stage_sla_end_day})",
			)
		for day, flag in ((overdue_day, "alert_150_sent"), (limit_day, "alert_180_sent")):
			if ageing >= day and not site.get(flag):
				digest.add([site.pm_user, site.am_user, *management], f"Site past {day} days", f"{link}: day {ageing}")
				frappe.db.set_value("UG Site", site.name, flag, 1, update_modified=False)

		for label, status, date, last in (
			("Length extension", "length_extension_status", "length_extension_request_date", "le_last_reminder"),
			("Rate revision", "rate_revision_status", "rate_revision_request_date", "rr_last_reminder"),
		):
			if site.get(status) == "Requested" and reminder_due(site.get(date), site.get(last)):
				digest.add([spoc_email], f"{label} reply pending", f"{link}: requested on {site.get(date)}")
				digest.add([site.pm_user, site.am_user, *management], f"{label}: no Airtel reply", f"{link}: requested on {site.get(date)}")
				frappe.db.set_value("UG Site", site.name, last, today(), update_modified=False)


def reminder_due(request_date, last_reminder):
	"""First reminder once Airtel has not replied for the set days, then every Monday."""
	if not request_date or date_diff(today(), request_date) < cint(get_setting("airtel_reply_days")):
		return False
	if not last_reminder:
		return True
	return getdate(today()).weekday() == 0 and getdate(last_reminder) < getdate(today())


def row_alerts(digest):
	row_team = get_role_users("UG ROW Team")
	accounts = get_role_users("UG Billing")
	apps = frappe.get_all(
		"ROW Application",
		filters={"permission_status": ("!=", "Received")},
		fields=["name", "ug_site", "node_id", "row_authority", "row_ageing", "expected_days", "sla_breached",
		        "next_followup_date", "responsible_person", "pm_user"],
	)
	for app in apps:
		link = f'<a href="{get_url_to_form("ROW Application", app.name)}">{app.name}</a> ({app.row_authority}, {app.node_id or app.ug_site})'
		if app.sla_breached:
			digest.add([*row_team, app.pm_user], "ROW delayed", f"{link}: {app.row_ageing} days (expected {app.expected_days})")
		if app.next_followup_date and getdate(app.next_followup_date) <= getdate(today()):
			digest.add([app.responsible_person], "ROW follow-up due", f"{link}: follow-up date {app.next_followup_date}")

	expiring = frappe.get_all(
		"ROW Application",
		filters={"bg_status": ("in", ["Expiring", "Expired"])},
		fields=["name", "row_authority", "bg_no", "bg_end_date", "bg_status"],
	)
	for app in expiring:
		link = f'<a href="{get_url_to_form("ROW Application", app.name)}">{app.name}</a> ({app.row_authority})'
		digest.add([*row_team, *accounts], "BG expiring", f"{link}: BG {app.bg_no or ''} {app.bg_status.lower()} on {app.bg_end_date}")


def punch_point_alerts(digest):
	limit = cint(get_setting("pp_ageing_alert_days"))
	atc = get_role_users("UG ATC Manager")
	pps = frappe.get_all(
		"UG Punch Point",
		filters={"status": ("!=", "Closed"), "date_assigned": ("<", add_days(today(), -limit))},
		fields=["name", "ug_site", "node_id", "pp_category", "current_ageing"],
	)
	for pp in pps:
		link = f'<a href="{get_url_to_form("UG Punch Point", pp.name)}">{pp.name}</a> ({pp.pp_category}, {pp.node_id or pp.ug_site})'
		digest.add(atc, "Punch point ageing", f"{link}: open {pp.current_ageing} days")
