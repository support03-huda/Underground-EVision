# Copyright (c) 2026, huda and contributors
"""Airtel PO — one Airtel purchase order. Attaching its PDF fills the header and lines
(`read_po_file`); Create / Update Sites pushes the lines onto the UG Sites they name, creating
sites that do not exist yet (`apply_to_sites`)."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from underground.po_reader import guess_work_type, parse_po_pdf

# Header fields copied from the parsed PDF onto the form.
HEADER_FIELDS = (
	"po_number",
	"po_no",
	"po_type",
	"po_date",
	"rev_no",
	"rev_date",
	"internal_ref",
	"buyer_name",
	"old_po_ref",
	"total_value",
	"payment_terms",
)
LINE_FIELDS = (
	"line_no",
	"item_code",
	"scope",
	"node_id",
	"description",
	"cwip_id",
	"need_by",
	"qty",
	"uom",
	"rate",
	"amount",
	"cgst",
	"sgst",
	"igst",
	"line_total",
	"gbpa_no",
	"sac",
)


class AirtelPO(Document):
	def validate(self):
		if self.replaces_po == self.name:
			frappe.throw(_("A PO cannot replace itself."))
		for line in self.lines:
			if not flt(line.amount):
				line.amount = flt(line.qty) * flt(line.rate)
			line.line_total = flt(line.line_total) or flt(line.amount) + tax(line)
			line.node_id = (line.node_id or "").strip() or None
			if not line.ug_site and line.node_id:
				line.ug_site = find_site(line.node_id)
		self.total_basic = sum(flt(line.amount) for line in self.lines)
		self.total_tax = sum(tax(line) for line in self.lines)
		if flt(self.total_value) and abs(self.total_basic + self.total_tax - flt(self.total_value)) > 1:
			frappe.msgprint(
				_("Lines add up to {0} with GST, but the PO prints {1}. Check the lines against the PDF.").format(
					frappe.format(self.total_basic + self.total_tax, {"fieldtype": "Currency"}),
					frappe.format(self.total_value, {"fieldtype": "Currency"}),
				),
				indicator="orange",
				alert=True,
			)


def tax(line):
	return flt(line.cgst) + flt(line.sgst) + flt(line.igst)


def find_site(node_id):
	"""The UG Site with this Node ID; failing that, one whose Node ID contains it (e.g. 'LOK2455/ROM912/MA265')."""
	if not node_id:
		return None
	return frappe.db.get_value("UG Site", {"node_id": node_id}) or frappe.db.get_value(
		"UG Site", {"node_id": ("like", f"%{node_id}%")}
	)


def previous_service_po(sites, exclude=None):
	"""Latest other Airtel PO (not Mobilization) already on any of these sites."""
	if not sites:
		return None
	line = frappe.qb.DocType("UG PO Line")
	rows = (
		frappe.qb.from_(line)
		.select(line.airtel_po)
		.distinct()
		.where(
			(line.parenttype == "UG Site")
			& (line.parent.isin(list(sites)))
			& (line.airtel_po.isnotnull())
			& (line.scope != "Mobilization")
			& (line.superseded == 0)
		)
		.run(pluck=True)
	)
	rows = [po for po in rows if po and po != exclude]
	if not rows:
		return None
	return frappe.get_all("Airtel PO", filters={"name": ("in", rows)}, order_by="po_date desc", limit=1, pluck="name")[0]


def parse_file(file_url):
	"""Parsed contents of an attached PO PDF (see underground.po_reader)."""
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	if not (file_doc.file_name or file_url).lower().endswith(".pdf"):
		frappe.throw(_("Attach the PO as a PDF file."))
	try:
		data = parse_po_pdf(file_doc.get_content())
	except Exception:
		frappe.log_error(title="Airtel PO: could not read PDF")
		frappe.throw(_("Could not read this PDF. Is it the PO PDF from Airtel's email (not a scan)?"))
	if not data.get("po_no") or not data.get("lines"):
		frappe.throw(_("No PO number or PO lines were found in this PDF. Enter the PO by hand."))
	return data


@frappe.whitelist()
def read_po_file(file_url):
	"""Parse an attached Airtel PO PDF and return the values for the form."""
	if not (frappe.has_permission("Airtel PO", "create") or frappe.has_permission("Airtel PO", "write")):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	data = parse_file(file_url)

	result = {field: data.get(field) for field in HEADER_FIELDS}
	result["lines"] = []
	for line in data["lines"]:
		row = {field: line.get(field) for field in LINE_FIELDS}
		row["ug_site"] = find_site(line.get("node_id"))
		result["lines"].append(row)

	work_types = {guess_work_type([l for l in data["lines"] if l.get("node_id") == node]) for node in
	              {l.get("node_id") for l in data["lines"]}} - {None, "MO"}
	if len(work_types) == 1 and frappe.db.exists("UG Work Type", next(iter(work_types))):
		result["work_type"] = next(iter(work_types))

	sites = {row["ug_site"] for row in result["lines"] if row["ug_site"]}
	if result["old_po_ref"] and frappe.db.exists("Airtel PO", result["old_po_ref"]):
		result["replaces_po"] = result["old_po_ref"]
	elif result["po_type"] == "Original":
		earlier = previous_service_po(sites, exclude=result["po_no"])
		if earlier:
			# Airtel does not print "rate revision" on these POs; an earlier PO on the same node means it is one.
			result["po_type"] = "Rate Revision"
			result["replaces_po"] = earlier
	result["already_exists"] = frappe.db.exists("Airtel PO", result["po_no"])
	return result


@frappe.whitelist()
def apply_to_sites(name):
	"""Put this PO's lines on their UG Sites (creating missing sites) and mark the replaced PO's lines superseded."""
	po = frappe.get_doc("Airtel PO", name)
	po.check_permission("write")
	if not po.lines:
		frappe.throw(_("This PO has no lines."))

	by_site = {}
	created = []
	for line in po.lines:
		site = line.ug_site or find_site(line.node_id)
		if not site:
			if not line.node_id:
				frappe.throw(_("Line {0} has no Node ID. Enter it or pick the UG Site.").format(line.idx))
			site = create_site(po, line)
			created.append(site)
		line.ug_site = site
		by_site.setdefault(site, []).append(line)

	for site_name, lines in by_site.items():
		site = frappe.get_doc("UG Site", site_name)
		site.set("po_lines", [row for row in site.po_lines if row.airtel_po != po.name])
		if po.replaces_po:
			for row in site.po_lines:
				if row.airtel_po == po.replaces_po:
					row.superseded = 1
		for line in lines:
			site.append("po_lines", site_line(po.name, po.po_type, line))
		if po.po_type != "Mobilization" or not site.po_number:
			site.po_number = po.po_number or po.po_no
		site.po_receipt_date = site.po_receipt_date or po.po_receipt_date
		site.po_start_date = site.po_start_date or po.po_date
		need_by = [line.need_by for line in lines if line.need_by]
		if need_by:
			site.po_end_date = max(need_by)
		site.po_copy = site.po_copy or po.po_file
		cwip = next((line.cwip_id for line in lines if line.cwip_id), None)
		site.cwip_id = site.cwip_id or cwip
		site.save()

	po.status = "Applied"
	po.save()
	return {"sites": list(by_site), "created": created}


def site_line(airtel_po, po_type, line):
	"""A UG Site PO Line from an Airtel PO line (a document or a dict of parsed values)."""
	line = frappe._dict(line.as_dict() if hasattr(line, "as_dict") else line)
	length = flt(line.qty) if line.scope == "T&D" and (line.uom or "").lower().startswith(("met", "mtr")) else 0
	return {
		"airtel_po": airtel_po,
		"po_type": po_type,
		"line_item": str(line.line_no or ""),
		"item_code": line.item_code,
		"scope": line.scope,
		"description": line.description,
		"qty": line.qty,
		"uom": line.uom,
		"rate": line.rate,
		"civil_length": length,
		"optical_length": length,
		"need_by": line.need_by,
		"tax_amount": tax(line),
		"line_total": line.line_total,
	}


def node_work_type(po, node_id):
	"""Work type read from this node's lines on the PO, if it is a known UG Work Type."""
	lines = [l.as_dict() for l in po.lines if l.node_id == node_id]
	work_type = guess_work_type(lines)
	return work_type if work_type and frappe.db.exists("UG Work Type", work_type) else None


def create_site(po, line):
	work_type = "MO" if line.scope == "Mobilization" else node_work_type(po, line.node_id) or po.work_type
	if not work_type:
		frappe.throw(
			_("Node {0} has no UG Site yet. Set the Work Type under Defaults for New Sites so it can be created.").format(
				line.node_id
			)
		)
	site = frappe.get_doc(
		{
			"doctype": "UG Site",
			"po_number": po.po_number or po.po_no,
			"po_receipt_date": po.po_receipt_date,
			"po_start_date": po.po_date,
			"nfa_no": po.internal_ref,
			"work_type": work_type,
			"node_id": line.node_id,
			"zone": po.zone,
			"district": po.district,
			"airtel_spoc": po.airtel_spoc,
			"project_manager": po.project_manager,
			"po_copy": po.po_file,
			"ibd_included": int(work_type == "LM" and any(l.scope == "IBD" and l.node_id == line.node_id for l in po.lines)),
		}
	).insert()
	return site.name
