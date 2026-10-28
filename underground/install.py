# Copyright (c) 2026, huda and contributors
"""Roles and starting masters for the UG Fiber ERP. Runs after install and after every
migrate; it only adds what is missing, so admin edits to these records are kept."""

import json

import frappe

ROLES = [
	"UG Admin",
	"UG Back Office",
	"UG Project Manager",
	"UG Area Manager",
	"UG Survey Team",
	"UG ROW Team",
	"UG Material Team",
	"UG Warehouse",
	"UG Execution Team",
	"UG Splicer",
	"UG Vendor",
	"UG ATC Manager",
	"UG Billing",
	"UG Management",
]

WORK_TYPES = [
	# work_type, description, needs_td, is_mobilization, scope
	("BB", "Backbone: main Airtel route linking nodes (bus, ring or star topology)", 1, 0, "T&D"),
	("LM", "Last Mile: from the tapping chamber up to the site antenna / tower", 1, 0, "T&D"),
	("Quality Patch", "Replaces a damaged stretch between two points A and B", 1, 0, "T&D"),
	("IBD", "In-Building: fiber run inside the building or tower", 0, 0, "IBD"),
	("FTTB", "Fiber to the Building: fiber taken inside the customer's building / office", 0, 0, "FTTB"),
	("MO", "Mobilization: compensation PO mapped against a node", 0, 1, "None"),
]

ROW_AUTHORITY_TYPES = [
	("GP", 40),
	("Nagarparishad", 40),
	("ZP", 40),
	("PWD", 40),
	("SH", 40),
	("NH", 50),
	("MIDC", 40),
	("MSRDC", 40),
	("Railway", 50),
	("Forest", 50),
	("Other", 40),
]

STAGE_SLAS = [
	# stage, start_day, end_day, tentative, owner_role
	("1 - PO Receipt", 0, 2, 0, "UG Back Office"),
	("2 - KMZ and Team", 0, 9, 0, "UG Back Office"),
	("3 - Survey and Feasibility", 7, 18, 0, "UG Project Manager"),
	("4 - SLD and Exceptions", 15, 35, 0, "UG Back Office"),
	("5 - CWIP, ROW, Job ID, VLC", 18, 75, 0, "UG ROW Team"),
	("6 - Material", 40, 65, 0, "UG Material Team"),
	("7 - Execution", 65, 150, 1, "UG Project Manager"),
	("8 - FF1, PP, ATC", 150, 160, 1, "UG ATC Manager"),
	("9 - Closure and Billing", 160, 180, 1, "UG Back Office"),
]

PP_CATEGORIES = [
	# category, counts as, default responsible party
	("Field", "Field", "RKBG"),
	("Document / Photo", "Document / Photo", "RKBG"),
	("Mail Approval", "Mail Approval", "Airtel"),
	("ROW", "ROW", "RKBG"),
	("Airtel Related", "Airtel", "Airtel"),
]

PP_SUB_CATEGORIES = [("Approval Pending", "Mail Approval"), ("Photographs Required", "Document / Photo")]

PAYMENT_MODES = ["Demand Draft", "NEFT / RTGS", "Online Portal", "Cheque", "Cash"]

MATERIAL_ITEMS = [
	# item, group, unit
	("Duct", "Duct", "Mtr"),
	("Optical Fiber Cable", "Cable", "Mtr"),
	("Simplex / End Plug", "Simplex / End Plug", "Nos"),
	("Coupler", "Coupler", "Nos"),
	("Closure", "Closure", "Nos"),
	("FDMS", "FDMS", "Nos"),
]


def after_install():
	create_roles()
	setup_assignment_board()
	setup_defaults()


def create_roles():
	"""Before migrate: the UG DocTypes' permissions name these roles."""
	for role in ROLES:
		insert_if_missing("Role", role, {"role_name": role, "desk_access": 1})
	frappe.db.commit()


BOARD_NAME = "UG Assignments"


def setup_assignment_board():
	"""Before migrate (the workspace links it) and after: the Assignments board on the Underground
	workspace is a Custom HTML Block built from underground/board/assignments.*, refreshed every time."""
	read = lambda ext: open(frappe.get_app_path("underground", "board", f"assignments.{ext}"), encoding="utf-8").read()
	values = {
		"html": read("html"),
		"script": read("js"),
		"style": read("css"),
		"private": 0,
		"roles": [{"role": role} for role in ("System Manager", *ROLES)],
	}
	if frappe.db.exists("Custom HTML Block", BOARD_NAME):
		doc = frappe.get_doc("Custom HTML Block", BOARD_NAME)
		doc.set("roles", [])
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Custom HTML Block", "__newname": BOARD_NAME, **values})
		doc.name = BOARD_NAME
		doc.insert(ignore_permissions=True)
	frappe.db.commit()


def setup_defaults():
	create_roles()
	for work_type, description, needs_td, is_mobilization, scope in WORK_TYPES:
		insert_if_missing(
			"UG Work Type",
			work_type,
			{
				"work_type": work_type,
				"description": description,
				"needs_td": needs_td,
				"is_mobilization": is_mobilization,
				"scope": scope,
			},
		)
	for authority_type, days in ROW_AUTHORITY_TYPES:
		insert_if_missing("ROW Authority Type", authority_type, {"authority_type": authority_type, "expected_days": days})
	for stage, start_day, end_day, tentative, owner_role in STAGE_SLAS:
		insert_if_missing(
			"UG Stage SLA",
			stage,
			{
				"stage": stage,
				"start_day": start_day,
				"end_day": end_day,
				"tentative": tentative,
				"owner_role": owner_role,
			},
		)
	for category, group, party in PP_CATEGORIES:
		insert_if_missing(
			"PP Category",
			category,
			{"category_name": category, "pp_group": group, "default_responsible_party": party},
		)
	for sub_category, category in PP_SUB_CATEGORIES:
		insert_if_missing("PP Sub Category", sub_category, {"sub_category_name": sub_category, "pp_category": category})
	for mode in PAYMENT_MODES:
		insert_if_missing("UG Payment Mode", mode, {"payment_mode": mode})
	for item, group, uom in MATERIAL_ITEMS:
		insert_if_missing("UG Material Item", item, {"item_name": item, "item_group": group, "uom": uom})
	setup_app_icon()
	rename_approved_assignments()
	frappe.db.commit()


def rename_approved_assignments():
	"""Assignments approved before the Assignments board (status "Approved") are now "In Progress"."""
	site = frappe.qb.DocType("UG Site")
	for field in ("am_approval_status", "splicer_approval_status"):
		if frappe.db.has_column("UG Site", field):
			frappe.qb.update(site).set(site[field], "In Progress").where(site[field] == "Approved").run()


def setup_app_icon():
	"""Show Underground as its own app on the desktop, with its logo.

	Frappe skips the app icon when a workspace icon already holds the "Underground" label,
	so that icon is turned into the app icon here."""
	if not frappe.db.exists("DocType", "Desktop Icon"):
		return
	values = {
		"icon_type": "App",
		"link_type": "External",
		"link": "/app/ug-dashboard",
		"app": "underground",
		"logo_url": "/assets/underground/images/underground-logo.svg",
		"bg_color": "blue",
		"hidden": 0,
		"parent_icon": None,
	}
	name = frappe.db.exists("Desktop Icon", "Underground")
	if name:
		frappe.db.set_value("Desktop Icon", name, values)
	else:
		frappe.get_doc({"doctype": "Desktop Icon", "label": "Underground", "standard": 1, **values}).insert(
			ignore_permissions=True
		)
	add_icon_to_saved_layouts(values)
	frappe.cache.delete_key("desktop_icons")


def add_icon_to_saved_layouts(values):
	"""A user who saved a desktop layout before this app was installed sees only that saved
	layout, so the Underground icon is appended to it."""
	if not frappe.db.exists("DocType", "Desktop Layout"):
		return
	for name, layout in frappe.get_all("Desktop Layout", fields=["name", "layout"], as_list=True):
		try:
			icons = json.loads(layout or "[]")
		except ValueError:
			continue
		if not isinstance(icons, list) or any(icon.get("label") == "Underground" for icon in icons):
			continue
		icons.append({"name": "Underground", "label": "Underground", "standard": 1, "idx": 0, "icon": None,
		              "link_to": None, "icon_image": None, "restrict_removal": 0, "child_icons": [], **values})
		frappe.db.set_value("Desktop Layout", name, "layout", json.dumps(icons), update_modified=False)
	frappe.cache.delete_key("bootinfo")


def insert_if_missing(doctype, name, values):
	if frappe.db.exists(doctype, name):
		return
	frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)
