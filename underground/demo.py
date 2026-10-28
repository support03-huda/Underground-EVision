# Copyright (c) 2026, huda and contributors
"""Four example UG sites at different stages, with their linked records, for training and testing.

	bench --site ug.local execute underground.demo.create
	bench --site ug.local execute underground.demo.delete

Every record is marked DEMO (node IDs DEMO-…, masters named "Demo …", users demo.…@example.com)
so delete() removes exactly what create() made. The sites move through the real gates in order,
so a demo that loads cleanly also shows the process rules hold. No site is given its Area
Manager: the system picks one from the site location and the demo areas (boundary or centre)."""

import io
import zipfile

import frappe
from frappe.utils import add_days, today
from frappe.utils.password import update_password

from underground.install import setup_defaults

NODES = ("DEMO-LM01", "DEMO-BB01", "DEMO-QP01", "DEMO-LM02")
DEMO_PASSWORD = "Demo@12345"
DEMO_FILES = ("demo-evidence.txt", "demo-pune-boundary.kml", "DEMO-LM02_MH.kmz")

# Site locations: Talegaon and Chakan fall inside the Pune boundary, Mangaon is nearest the
# Raigad centre, and the new LM02 site (route copied from a real Airtel KMZ) the Ahmednagar centre.
LOCATIONS = {
	"DEMO-LM01": (18.7341, 73.6752),
	"DEMO-BB01": (18.2333, 73.2833),
	"DEMO-QP01": (18.7606, 73.8636),
}
PUNE_BOUNDARY = [(73.40, 18.40), (74.10, 18.40), (74.10, 19.00), (73.40, 19.00), (73.40, 18.40)]
LM02_SITE = (74.232616, 19.16281)
LM02_TAPPING = (74.234608, 19.16273)
LM02_PROPOSED = [
	(74.234604, 19.162751), (74.234681, 19.162725), (74.234461, 19.162515), (74.234319, 19.162409),
	(74.233979, 19.162197), (74.233381, 19.161856), (74.232929, 19.161605), (74.232923, 19.161776),
	(74.232994, 19.162475), (74.233035, 19.162695), (74.232784, 19.162717), (74.232746, 19.162824),
	(74.232606, 19.162827),
]
LM02_EXISTING = [
	(74.234835, 19.163026), (74.234617, 19.162764), (74.234418, 19.162566), (74.234096, 19.162341),
	(74.233877, 19.162216), (74.233167, 19.161803), (74.232608, 19.161475),
]


def day(offset):
	return add_days(today(), offset)


def create():
	if frappe.db.exists("UG Site", {"node_id": ("in", NODES)}):
		print("Demo data already exists. Run underground.demo.delete first to recreate it,")
		print("or underground.demo.create_users to add only the test logins.")
		return
	setup_defaults()
	users()
	masters()
	evidence = evidence_file()
	site_a = site_in_execution()
	site_b = site_waiting_on_row()
	site_c = site_ready_for_billing(evidence)
	site_d = site_new_with_kmz()
	frappe.db.commit()
	for name in (site_a, site_b, site_c, site_d):
		site = frappe.db.get_value(
			"UG Site", name, ["node_id", "current_stage", "site_ageing", "zone", "area_manager"], as_dict=True
		)
		print(f"{name}  {site.node_id:<10}  {site.current_stage:<28}  day {site.site_ageing:<4}"
		      f"  {site.zone} / {site.area_manager}")
	print(f"\nTest logins (password {DEMO_PASSWORD}):")
	for email, name, role, _employee in DEMO_USERS:
		print(f"  {email:<34} {role}")


# ---------------------------------------------------------------- users
DEMO_USERS = [
	# email, name, role, UG Employee / UG Splicer / UG Vendor it belongs to
	("demo.pm@example.com", "Demo PM", "UG Project Manager", "Demo Project Manager"),
	("demo.am.pune@example.com", "Demo AM Pune", "UG Area Manager", "Demo AM Pune A"),
	("demo.am.raigad@example.com", "Demo AM Raigad", "UG Area Manager", "Demo AM Raigad"),
	("demo.splicer@example.com", "Demo Splicer", "UG Splicer", "Demo Splicer"),
	("demo.backoffice@example.com", "Demo Back Office", "UG Back Office", None),
	("demo.vendor@example.com", "Demo Vendor", "UG Vendor", "Demo Civil Works"),
]


def users():
	for email, name, role, _employee in DEMO_USERS:
		if frappe.db.exists("User", email):
			continue
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": name,
				"user_type": "System User",
				"send_welcome_email": 0,
				"roles": [{"role": role}],
			}
		).insert(ignore_permissions=True)
		update_password(email, DEMO_PASSWORD)


def demo_user(employee):
	return next((email for email, _n, _r, e in DEMO_USERS if e == employee), None)


def create_users():
	"""Only the test logins, linked to the demo masters that already exist.

	bench --site ug.local execute underground.demo.create_users"""
	users()
	for email, _name, _role, linked in DEMO_USERS:
		for doctype in ("UG Employee", "UG Splicer", "UG Vendor"):
			if linked and frappe.db.exists(doctype, linked):
				frappe.db.set_value(doctype, linked, "user", email)
	frappe.db.commit()
	# Sites fetch the users from their PM / Area Manager / Splicer: re-save to pick them up.
	for name in frappe.get_all("UG Site", filters={"node_id": ("in", NODES)}, pluck="name"):
		try:
			frappe.get_doc("UG Site", name).save(ignore_permissions=True)
		except frappe.ValidationError as e:
			frappe.db.rollback()
			print(f"  {name} not updated ({e}). Recreate the demo: underground.demo.delete, then create.")
	frappe.db.commit()
	print(f"Test logins (password {DEMO_PASSWORD}):")
	for email, _name, role, _linked in DEMO_USERS:
		print(f"  {email:<34} {role}  {'ok' if frappe.db.exists('User', email) else 'MISSING'}")


# ---------------------------------------------------------------- masters
def masters():
	# Pune has a boundary polygon; Raigad and Ahmednagar only a centre and coverage radius.
	boundary = demo_file("demo-pune-boundary.kml", boundary_kml("Demo Pune", PUNE_BOUNDARY))
	add("UG Zone", "Demo Pune", zone_name="Demo Pune", boundary_kmz=boundary)
	add("UG Zone", "Demo Raigad", zone_name="Demo Raigad", center_latitude=18.25, center_longitude=73.30,
	    coverage_km=60)
	add("UG Zone", "Demo Ahmednagar", zone_name="Demo Ahmednagar", center_latitude=19.09,
	    center_longitude=74.74, coverage_km=90)
	add("UG District", "Demo Pune District", district_name="Demo Pune District", zone="Demo Pune")
	add("UG District", "Demo Raigad District", district_name="Demo Raigad District", zone="Demo Raigad")
	add("UG Route", "Demo Talegaon-Chakan", route_name="Demo Talegaon-Chakan", zone="Demo Pune",
	    district="Demo Pune District")
	add("UG Route", "Demo Mangaon-Mahad", route_name="Demo Mangaon-Mahad", zone="Demo Raigad",
	    district="Demo Raigad District")
	add("Airtel SPOC", "Demo Airtel SPOC", spoc_name="Demo Airtel SPOC", zone="Demo Pune",
	    phone="9000000001", email="demo.spoc@example.com")
	add("UG Employee", "Demo Project Manager", employee_name="Demo Project Manager",
	    designation="Project Manager", zone="Demo Pune", mobile_no="9000000002",
	    user=demo_user("Demo Project Manager"))
	# Two Area Managers in Pune: the system gives each new site to the one with fewer sites.
	for name, zone, mobile in (
		("Demo AM Pune A", "Demo Pune", "9000000003"),
		("Demo AM Pune B", "Demo Pune", "9000000006"),
		("Demo AM Raigad", "Demo Raigad", "9000000007"),
		("Demo AM Ahmednagar", "Demo Ahmednagar", "9000000008"),
	):
		add("UG Employee", name, employee_name=name, designation="Area Manager", zone=zone, mobile_no=mobile,
		    user=demo_user(name))
	add("UG Vendor", "Demo Civil Works", vendor_name="Demo Civil Works", vendor_type="All Work",
	    contact_person="Demo Contact", contact_no="9000000004", user=demo_user("Demo Civil Works"))
	# The vendor assigns one of its splicers to each site.
	add("UG Splicer", "Demo Splicer", splicer_name="Demo Splicer", vendor="Demo Civil Works",
	    mobile_no="9000000005", has_splicing_machine=1, has_otdr=1, user=demo_user("Demo Splicer"))
	add("UG Splicer", "Demo Splicer Two", splicer_name="Demo Splicer Two", vendor="Demo Civil Works",
	    mobile_no="9000000009", has_splicing_machine=1)
	add("ROW Authority", "Demo Gram Panchayat", authority_name="Demo Gram Panchayat", authority_type="GP",
	    district="Demo Pune District")
	add("ROW Authority", "Demo PWD Division", authority_name="Demo PWD Division", authority_type="PWD",
	    district="Demo Raigad District")
	add("ROW Authority", "Demo NHAI Office", authority_name="Demo NHAI Office", authority_type="NH",
	    district="Demo Raigad District")
	add("UG Warehouse", "Demo Bhiwandi Warehouse", warehouse_name="Demo Bhiwandi Warehouse",
	    zone="Demo Pune")
	add("UG Cable Type", "24F", cable_type="24F")
	add("UG Duct Colour", "Orange", duct_colour="Orange")


def add(doctype, name, **values):
	if not frappe.db.exists(doctype, name):
		frappe.get_doc({"doctype": doctype, **values}).insert(ignore_permissions=True)


def evidence_file():
	return demo_file("demo-evidence.txt", "Demo evidence attachment for UG demo punch points.")


def demo_file(file_name, content):
	file = frappe.get_doc(
		{"doctype": "File", "file_name": file_name, "content": content, "is_private": 1}
	).insert(ignore_permissions=True)
	return file.file_url


def coordinates(points):
	return " ".join(f"{lon},{lat},0" for lon, lat in points)


def boundary_kml(name, ring):
	return (
		'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
		f"<Placemark><name>{name}</name><Polygon><outerBoundaryIs><LinearRing><coordinates>"
		f"{coordinates(ring)}</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark>"
		"</Document></kml>"
	)


def site_kmz(node):
	"""A KMZ laid out like Airtel's: site point, tapping point, proposed and existing route."""
	placemarks = [
		(node, f"<Point><coordinates>{coordinates([LM02_SITE])}</coordinates></Point>"),
		("TTSL Joint Chamber", f"<Point><coordinates>{coordinates([LM02_TAPPING])}</coordinates></Point>"),
		(f"{node} Proposed OFC Route", f"<LineString><coordinates>{coordinates(LM02_PROPOSED)}</coordinates></LineString>"),
		("TTSL Existing OFC Route", f"<LineString><coordinates>{coordinates(LM02_EXISTING)}</coordinates></LineString>"),
	]
	kml = (
		'<?xml version="1.0" encoding="UTF-8"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document>'
		f"<name>{node}_MH.kmz</name><Folder><name>{node}_MH</name>"
		+ "".join(f"<Placemark><name>{name}</name>{geometry}</Placemark>" for name, geometry in placemarks)
		+ "</Folder></Document></kml>"
	)
	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as kmz:
		kmz.writestr("doc.kml", kml)
	return buffer.getvalue()


def common_site(node_id, node_name, receipt_offset, work_type, zone, district, route, lines, **values):
	latitude, longitude = LOCATIONS[node_id]
	return {
		"doctype": "UG Site",
		"po_number": f"TNL-FF-Maharashtra/PUR/DEMO{node_id[-4:]}",
		"po_receipt_date": day(receipt_offset),
		"po_start_date": day(receipt_offset),
		"po_end_date": day(receipt_offset + 180),
		"work_type": work_type,
		"zone": zone,
		"district": district,
		"airtel_spoc": "Demo Airtel SPOC",
		"po_lines": lines,
		"kmz_received": 1,
		"kmz_received_date": day(receipt_offset + 4),
		"node_id": node_id,
		"node_name": node_name,
		"route": route,
		"kmz_latitude": latitude,
		"kmz_longitude": longitude,
		"kmz_tapping_point": "Airtel chamber",
		"project_manager": "Demo Project Manager",
		"team_vendor": "Demo Civil Works",
		"survey_planned_date": day(receipt_offset + 8),
		"survey_actual_date": day(receipt_offset + 11),
		"survey_status": "Completed",
		"survey_tapping_point": "Airtel chamber",
		"survey_latitude": latitude,
		"survey_longitude": longitude,
		"site_feasibility": "Feasible",
		"sld_prepared": 1,
		"airtel_sld_signature": "Received",
		"rkbg_sld_signature": "Received",
		"sld_upload_date": day(receipt_offset + 19),
		"airtel_works_upload_status": "Accepted",
		**values,
	}


def po_line(item_code, description, qty, rate, scope="T&D"):
	length = qty if scope == "T&D" else 0
	return {
		"item_code": item_code,
		"scope": scope,
		"description": description,
		"qty": qty,
		"uom": "Meter",
		"rate": rate,
		"civil_length": length,
		"optical_length": length,
	}


def row_application(site, authority, authority_type, offset, **values):
	return frappe.get_doc(
		{
			"doctype": "ROW Application",
			"ug_site": site,
			"row_authority": authority,
			"authority_type": authority_type,
			"application_mode": "Online",
			"application_no": f"DEMO/ROW/{authority_type}/{offset}",
			"application_status": "Submitted",
			"application_date": day(offset),
			**values,
		}
	).insert(ignore_permissions=True)


def material(site, offset, cable_qty, duct_qty):
	frappe.get_doc(
		{
			"doctype": "UG Material Order",
			"material_order_no": f"DEMO-MO-{site[-5:]}",
			"order_email_date": day(offset),
			"warehouse": "Demo Bhiwandi Warehouse",
			"material_received_date": day(offset + 10),
			"delivery_challan_no": f"DEMO-DC-{site[-5:]}",
			"items": [
				{"ug_site": site, "item": "Optical Fiber Cable", "cable_type": "24F", "ordered_qty": cable_qty,
				 "received_qty": cable_qty},
				{"ug_site": site, "item": "Duct", "duct_colour": "Orange", "ordered_qty": duct_qty,
				 "received_qty": duct_qty},
				{"ug_site": site, "item": "Coupler", "ordered_qty": 20, "received_qty": 20},
			],
		}
	).insert(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": "UG Material Dispatch",
			"dispatch_date": day(offset + 12),
			"dispatched": 1,
			"dispatch_to_type": "Vendor / Team",
			"dispatch_to_vendor": "Demo Civil Works",
			"warehouse": "Demo Bhiwandi Warehouse",
			"vehicle_no": "MH12 DE 0001",
			"items": [
				{"ug_site": site, "item": "Optical Fiber Cable", "qty": cable_qty},
				{"ug_site": site, "item": "Duct", "qty": duct_qty},
				{"ug_site": site, "item": "Coupler", "qty": 20},
			],
		}
	).insert(ignore_permissions=True)


def update(site, **values):
	doc = frappe.get_doc("UG Site", site)
	doc.update(values)
	doc.save(ignore_permissions=True)
	return doc


def progress(site, offset, td_km, blowing_km, ibd_m=0, chainage=""):
	frappe.get_doc(
		{
			"doctype": "UG Daily Progress",
			"ug_site": site,
			"progress_date": day(offset),
			"vendor": "Demo Civil Works",
			"td_km": td_km,
			"cable_blowing_km": blowing_km,
			"ibd_m": ibd_m,
			"section_chainage": chainage,
			"remarks": "Demo progress entry",
		}
	).insert(ignore_permissions=True)


# ---------------------------------------------------------------- site A: LM + IBD, in execution
def site_in_execution():
	"""Day ~95: ROW received, Job ID and VLC done, material dispatched, T&D under way."""
	site = frappe.get_doc(
		common_site(
			"DEMO-LM01", "Demo Talegaon Tower", -95, "LM", "Demo Pune", "Demo Pune District",
			"Demo Talegaon-Chakan",
			[
				po_line("NET005417", "End to End Execution node/LM/Quality/FTTB Connectivity -Length <=1Km DEMO-LM01", 800, 485),
				po_line("NET005434", "In building Work on node/LM/Quality/FTTB Connectivity DEMO-LM01", 20, 125, "IBD"),
			],
			ibd_included=1,
			ibd_scope_m=20,
			survey_length=780,
			row_required="Yes",
			row_authorities=[{"row_authority": "Demo Gram Panchayat", "chainage": "0.000-0.780", "row_length_km": 0.78}],
			cwip_id="CWIP-DEMO-001",
			cwip_mapping_status="Correct",
		)
	).insert(ignore_permissions=True)
	row_application(
		site.name, "Demo Gram Panchayat", "GP", -72,
		demand_note_no="DEMO-DN-001", demand_note_date=day(-60), demand_note_amount=15000,
		demand_note_status="Paid", payment_required=1, paid_by="RKBG", payment_amount=15000,
		payment_mode="Demand Draft", payment_reference="DD-DEMO-001", payment_date=day(-55),
		permission_status="Received", permission_date=day(-40),
	)
	update(site.name, job_id="JOB-DEMO-001", job_id_mapping_status="Correct", job_id_approval_status="Approved")
	update(site.name, vlc_request_date=day(-50), vlc_code="61027.TNGC.DEMO01.CONT1252", vlc_status="Received")
	material(site.name, -45, 800, 800)
	update(site.name, execution_vendor="Demo Civil Works", execution_release_date=day(-20),
	       execution_start_date=day(-18), current_blocker="", next_action="Complete T&D from chainage 0.55")
	progress(site.name, -15, 0.20, 0, chainage="0.000-0.200")
	progress(site.name, -10, 0.18, 0.15, chainage="0.200-0.380")
	progress(site.name, -5, 0.17, 0.20, ibd_m=10, chainage="0.380-0.550")
	return site.name


# ---------------------------------------------------------------- site B: BB, waiting on ROW
def site_waiting_on_row():
	"""Day ~60: survey longer than PO (length extension requested), two authorities, one still pending."""
	site = frappe.get_doc(
		common_site(
			"DEMO-BB01", "Demo Mangaon Backbone", -60, "BB", "Demo Raigad", "Demo Raigad District",
			"Demo Mangaon-Mahad",
			[po_line("ICW000004", "OFC laying, Trenching & Digging work for Inter-city Connectivity DEMO-BB01", 3500, 340)],
			survey_length=3650,
			length_extension_recommended=1,
			recommended_length=3650,
			length_extension_status="Requested",
			length_extension_request_date=day(-40),
			followups=[
				{"request_type": "Length Extension", "followup_date": day(-40), "mode": "Email",
				 "person_contacted": "Demo Airtel SPOC", "outcome": "Request sent with survey SLD"},
				{"request_type": "Length Extension", "followup_date": day(-30), "mode": "Call",
				 "person_contacted": "Demo Airtel SPOC", "outcome": "Under review at circle office"},
			],
			row_required="Yes",
			row_authorities=[
				{"row_authority": "Demo PWD Division", "chainage": "0.000-2.100", "row_length_km": 2.1},
				{"row_authority": "Demo NHAI Office", "chainage": "2.100-3.650", "row_length_km": 1.55},
			],
			cwip_id="CWIP-DEMO-002",
			cwip_mapping_status="Correct",
			current_blocker="NHAI permission pending; length extension awaiting Airtel",
			next_action="Follow up NHAI on demand note",
		)
	).insert(ignore_permissions=True)
	row_application(
		site.name, "Demo PWD Division", "PWD", -38,
		demand_note_no="DEMO-DN-002", demand_note_date=day(-28), demand_note_amount=42000,
		demand_note_status="Paid", payment_required=1, paid_by="RKBG", payment_amount=42000,
		payment_mode="Demand Draft", payment_reference="DD-DEMO-002", payment_date=day(-24),
		sd_required=1, sd_amount=25000, sd_deposit_date=day(-24),
		permission_status="Received", permission_date=day(-12),
	)
	row_application(
		site.name, "Demo NHAI Office", "NH", -36,
		demand_note_status="Not Received",
		bg_required=1, bg_no="BG-DEMO-001", bg_bank="Demo Bank", bg_amount=100000,
		bg_start_date=day(-330), bg_end_date=day(20),
		current_blocker="Demand note awaited from NHAI",
		next_followup_date=today(), responsible_person="Administrator",
	)
	update(site.name, job_id="JOB-DEMO-002", job_id_mapping_status="Pending")
	return site.name


# ---------------------------------------------------------------- site C: Quality Patch, ready for billing
def site_ready_for_billing(evidence):
	"""Day ~170: built, FF1 submitted, punch points cleared, ATC ready, approvals in, invoice submitted."""
	site = frappe.get_doc(
		common_site(
			"DEMO-QP01", "Demo Chakan Quality Patch", -170, "Quality Patch", "Demo Pune", "Demo Pune District",
			"Demo Talegaon-Chakan",
			[po_line("ICW000004", "OFC laying, Trenching & Digging work Quality/CWIP-DEMO-003 DEMO-QP01", 500, 370)],
			survey_length=480,
			row_required="No",
			row_not_required_reason="Quality patch inside existing Airtel duct corridor",
			cwip_id="CWIP-DEMO-003",
			cwip_mapping_status="Correct",
		)
	).insert(ignore_permissions=True)
	update(site.name, job_id="JOB-DEMO-003", job_id_mapping_status="Correct", job_id_approval_status="Approved")
	update(site.name, vlc_request_date=day(-140), vlc_code="61027.TNGQ.DEMO03.CONT1252", vlc_status="Received")
	material(site.name, -130, 500, 500)
	update(site.name, execution_vendor="Demo Civil Works", execution_release_date=day(-105),
	       execution_start_date=day(-100))
	progress(site.name, -95, 0.25, 0, chainage="0.000-0.250")
	progress(site.name, -90, 0.23, 0.48, chainage="0.250-0.480")
	update(site.name, splicing_status="Completed", splicer="Demo Splicer", fdms_status="Completed",
	       otdr_status="Passed", final_photos_status="Received", execution_documents_status="Complete")
	update(site.name, ff1_submission_status="Submitted", ff1_submission_date=day(-25),
	       airtel_compliance_status="PP Raised")
	for category, issue, action in (
		("Field", "Route marker missing at chainage 0.300", "Route marker installed, photo attached"),
		("Document / Photo", "Splicing photographs required in FF1", "Photographs uploaded to Airtel Works"),
	):
		frappe.get_doc(
			{
				"doctype": "UG Punch Point",
				"ug_site": site.name,
				"pp_category": category,
				"issue_description": issue,
				"action_required": "Clear and attach evidence",
				"action_taken": action,
				"responsible_party": "RKBG",
				"date_assigned": day(-20),
				"nc_resolved_date": day(-12),
				"status": "Closed",
				"evidence": evidence,
			}
		).insert(ignore_permissions=True)
	doc = frappe.get_doc("UG Site", site.name)
	for row in doc.site_materials:
		row.consumed_qty = {"Optical Fiber Cable": 490, "Duct": 485}.get(row.item, row.received_qty)
	doc.update(
		{
			"airtel_compliance_status": "Compliant",
			"atc_status": "Ready",
			"atc_date": day(-8),
			"reconciliation_status": "Approved",
			"mrs_mail_sent_date": day(-10),
			"mrs_approval_date": day(-6),
			"zonal_approval_status": "Approved",
			"central_approval_status": "Approved",
			"commitment_date": day(10),
			"short_summary": "Billing submitted; handover after invoice approval",
		}
	)
	doc.save(ignore_permissions=True)
	update(site.name, billing_status="Submitted", invoice_number="DEMO-INV-001", invoice_date=day(-2),
	       invoice_amount=185000)
	return site.name


# ---------------------------------------------------------------- site D: new LM, KMZ just received
def site_new_with_kmz():
	"""Day ~3: PO in, KMZ attached. The system reads the KMZ (location, tapping point, route length,
	map), finds the area from the location and assigns its Area Manager. The KMZ route (407 m) is
	longer than the PO (350 m), so a length extension is flagged."""
	kmz = demo_file("DEMO-LM02_MH.kmz", site_kmz("DEMO-LM02"))
	return frappe.get_doc(
		{
			"doctype": "UG Site",
			"po_number": "TNL-FF-Maharashtra/PUR/DEMOLM02",
			"po_receipt_date": day(-3),
			"po_start_date": day(-3),
			"po_end_date": day(177),
			"work_type": "LM",
			"airtel_spoc": "Demo Airtel SPOC",
			"po_lines": [
				po_line("NET005417", "End to End Execution node/LM/Quality/FTTB Connectivity -Length <=1Km DEMO-LM02", 350, 485),
			],
			"node_id": "DEMO-LM02",
			"node_name": "Demo Parner Tower",
			"kmz_file": kmz,
			"project_manager": "Demo Project Manager",
		}
	).insert(ignore_permissions=True).name


# ---------------------------------------------------------------- cleanup
def delete():
	sites = frappe.get_all("UG Site", filters={"node_id": ("in", NODES)}, pluck="name")
	for doctype in ("UG Daily Progress", "UG Punch Point", "ROW Application", "UG Material Request"):
		for name in frappe.get_all(doctype, filters={"ug_site": ("in", sites or [""])}, pluck="name"):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	for doctype, child in (("UG Material Dispatch", "UG Material Dispatch Item"), ("UG Material Order", "UG Material Order Item")):
		table = frappe.qb.DocType(child)
		parents = set(
			frappe.qb.from_(table).select(table.parent).where(table.ug_site.isin(sites or [""])).run(pluck=True)
		)
		for name in parents:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	for name in sites:
		frappe.delete_doc("UG Site", name, force=True, ignore_permissions=True)
	for doctype, field in (
		("ROW Authority", "authority_name"),
		("UG Route", "route_name"),
		("UG District", "district_name"),
		("UG Warehouse", "warehouse_name"),
		("UG Splicer", "splicer_name"),
		("UG Vendor", "vendor_name"),
		("UG Employee", "employee_name"),
		("Airtel SPOC", "spoc_name"),
		("UG Zone", "zone_name"),
	):
		for name in frappe.get_all(doctype, filters={field: ("like", "Demo %")}, pluck="name"):
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True)
	for name in frappe.get_all("File", filters={"file_name": ("in", DEMO_FILES)}, pluck="name"):
		frappe.delete_doc("File", name, force=True, ignore_permissions=True)
	for email, *_rest in DEMO_USERS:
		if frappe.db.exists("User", email):
			frappe.delete_doc("User", email, force=True, ignore_permissions=True)
	frappe.db.commit()
	print(f"Deleted {len(sites)} demo site(s) and their records.")
