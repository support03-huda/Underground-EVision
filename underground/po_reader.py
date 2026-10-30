# Copyright (c) 2026, huda and contributors
"""Reads an Airtel purchase order PDF (Oracle iSupplier layout) into a dict that fills an
Airtel PO: header, payment terms and one entry per line with qty, rate, GST and node ID.

`parse_po_text` has no Frappe dependency so it can be tested on plain text."""

import io
import re
from datetime import datetime

LINE_START = re.compile(r"^\s*(\d{1,3})\s+([A-Z0-9]{6,})\s+-\s+", re.M)
FIGURES = re.compile(
	r"(\d{2}-[A-Z]{3}-\d{2,4})\s+([\d,]+(?:\.\d+)?)\s+([A-Za-z]+)\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s*$", re.M
)
TAX = re.compile(r"\b(CGST|SGST|IGST|UTGST)_(\d+(?:\.\d+)?)%\S*\s+([\d,]+(?:\.\d+)?)")
# Repeated on every page; dropped before the lines are read.
PAGE_NOISE = re.compile(
	r"^\s*(Regd Office:.*|Mumbai IN \d+|Purchase Order Continuation Sheet|PO No:.*|Partner Name:.*|Page \d+ of \d+)\s*$",
	re.M,
)
NODE_PATTERNS = [
	re.compile(r"Node\s*I[dD]\s*[-:]?\s*([A-Z0-9][A-Z0-9/_-]*[A-Z0-9])"),
	re.compile(r"\b(?:MH-)([A-Z]{2,4}\d{2,5})\b"),
	re.compile(r"\b([A-Z]{2,4}\d{3,5})\b"),
]


def read_pdf_text(content):
	from pypdf import PdfReader

	reader = PdfReader(io.BytesIO(content))
	return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_po_pdf(content):
	return parse_po_text(read_pdf_text(content))


def parse_po_text(text):
	header = parse_header(text)
	body = PAGE_NOISE.sub("", text)
	start = body.find("S.No Item / Item Description")
	end = body.find("Total PO Value:", start)
	lines = parse_lines(body[start:end] if start >= 0 else body)
	header["lines"] = lines
	header["total_basic"] = round(sum(line["amount"] for line in lines), 2)
	header["total_tax"] = round(sum(line["cgst"] + line["sgst"] + line["igst"] for line in lines), 2)
	header["po_type"] = guess_po_type(text)
	return header


def parse_header(text):
	po_number = find(r"PO No\.\s*:\s*(\S+)", text)
	internal_ref = find(r"Internal Ref No\s*:\s*(\S+)", text)
	return {
		"po_number": po_number,
		"po_no": find(r"(\d+)\s*$", po_number or "") or po_number,
		"po_date": to_date(find(r"PO Date\s*:\s*(\d{2}-[A-Z]{3}-\d{2,4})", text)),
		"rev_no": int(find(r"Rev No\.\s*:\s*(\d+)", text) or 0),
		"rev_date": to_date(find(r"Rev Date\s*:\s*(\d{2}-[A-Z]{3}-\d{2,4})", text)),
		"internal_ref": re.sub(r"^-?\d+-", "", internal_ref or "") or None,
		"total_value": to_number(find(r"Total Purchase Order Value\s*:\s*([\d,]+(?:\.\d+)?)", text)),
		"payment_terms": squash(find(r"Payment terms\s*:\s*(.*?)\n\s*Installation", text, re.S)),
		"buyer_name": squash(find(r"Buyer Name\s*:\s*([^\n]+)", text)),
		"old_po_ref": find(r"Old\s+PO\s+No\.?\s*[-:]?\s*(\d{6,})", squash(text)),
	}


def parse_lines(section):
	starts = list(LINE_START.finditer(section))
	lines = []
	for i, match in enumerate(starts):
		block = section[match.start() : starts[i + 1].start() if i + 1 < len(starts) else len(section)]
		figures = FIGURES.search(block)
		if not figures:
			continue
		need_by, qty, uom, rate, amount = figures.groups()
		text_start = match.end() - match.start()
		text_end = block.find("HSN Number") if "HSN Number" in block else figures.start()
		description = squash(block[text_start:text_end]) or ""
		taxes = {"cgst": 0.0, "sgst": 0.0, "igst": 0.0}
		for kind, _rate, value in TAX.findall(block):
			key = "igst" if kind == "IGST" else "sgst" if kind in ("SGST", "UTGST") else "cgst"
			taxes[key] += to_number(value)
		amount = to_number(amount)
		lines.append(
			{
				"line_no": int(match.group(1)),
				"item_code": match.group(2),
				"description": description,
				"scope": guess_scope(description),
				"node_id": guess_node_id(description),
				"cwip_id": find(r"\b(CWIP-\d+)", description),
				"need_by": to_date(need_by),
				"qty": to_number(qty),
				"uom": uom,
				"rate": to_number(rate),
				"amount": amount,
				**taxes,
				"line_total": to_number(find(r"Total Line Value\s+([\d,]+(?:\.\d+)?)", block))
				or amount + sum(taxes.values()),
				"gbpa_no": find(r"GBPA No\s*:\s*-?\s*(\d+)", block),
				"sac": find(r"SAC Number:\s*(\d+)", block),
			}
		)
	return lines


def guess_scope(description):
	text = description.lower()
	if "mobilization" in text or "mobilisation" in text:
		return "Mobilization"
	if "in building" in text or "in-building" in text:
		return "IBD"
	if "splicing" in text:
		return "Splicing"
	return "T&D"


def site_part(description):
	"""The text after Airtel's rate-card wording, which names the site, e.g. 'FTTB John Deere ...'.
	The rate card itself lists 'node/LM/Quality/FTTB Connectivity' on every line, so it says nothing."""
	text = re.split(r"HSN Number", description or "")[0]
	parts = re.split(r"(?i)connectivity|per fiber", text)
	return parts[-1].lower() if len(parts) > 1 else text.lower()


def guess_work_type(lines):
	"""Work type of one node from its PO lines; the user confirms it on the form.
	Checked against the client's MASTER sheet, where the site part decides the category."""
	scopes = {line.get("scope") for line in lines}
	if scopes == {"Mobilization"}:
		return "MO"
	lines = [line for line in lines if line.get("scope") != "Mobilization"]
	site = " ".join(site_part(line.get("description")) for line in lines)
	if "ftth" in site:
		return "FTTH"
	if "fttb" in site or "Splicing" in scopes:
		return "FTTB"
	if re.search(r"back\s*bone|\bnld\b", site):
		return "BB"
	if "quality" in site:
		return "Quality Patch"
	if any(guess_node_id(line.get("description") or "") for line in lines):
		return "IBD" if scopes == {"IBD"} else "LM"
	# A CWIP route with no node named is a patch on an existing route.
	if re.search(r"cwip-\d+", site):
		return "Quality Patch"
	# No Airtel node named: the line names a customer building (e.g. 'Joyville Hadapsar').
	return "FTTB" if lines else None


def guess_po_type(text):
	flat = squash(text).lower()
	if "mobilization amount" in flat or "mobilisation amount" in flat:
		return "Mobilization"
	if "length amendment" in flat or "old po no" in flat:
		return "Length Amendment"
	if "rate revision" in flat:
		return "Rate Revision"
	return "Original"


def guess_node_id(description):
	"""The site part follows the rate-card text, e.g. 'Node Id-LOK2455/ROM912/MA265' or a bare 'TMP6161'."""
	for pattern in NODE_PATTERNS:
		match = pattern.search(description)
		if match:
			return match.group(1)
	return None


def find(pattern, text, flags=0):
	match = re.search(pattern, text or "", flags)
	return match.group(1).strip() if match else None


def squash(text):
	return re.sub(r"\s+", " ", text or "").strip() or None


def to_number(value):
	return float(str(value).replace(",", "")) if value else 0.0


def to_date(value):
	if not value:
		return None
	for fmt in ("%d-%b-%y", "%d-%b-%Y"):
		try:
			return datetime.strptime(value.title(), fmt).strftime("%Y-%m-%d")
		except ValueError:
			continue
	return None
