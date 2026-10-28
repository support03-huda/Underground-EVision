# Copyright (c) 2026, huda and contributors
"""Report Maker: any UG list (sites, POs, ROW, progress, material, cable, punch points, masters)
or any of the ready UG reports, with the columns, filters, sorting, grouping and totals the user
picks; previewed on screen and downloaded as Excel, PDF, Word or CSV. Every row goes through the
user's normal permissions, so a Project Manager still gets only their own sites."""

import csv
import io
import json
import re

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.utils import cint, flt, fmt_money, format_datetime, formatdate, now_datetime, strip_html

# Lists: (label, doctype, parent doctype for child tables)
SOURCES = [
	("Sites", "UG Site", None),
	("Site PO Lines", "UG PO Line", "UG Site"),
	("Site ROW Authorities", "UG Site ROW Authority", "UG Site"),
	("Site Material (Received / Consumed)", "UG Site Material", "UG Site"),
	("Fibre Cable Laid (Cable ID, Readings)", "UG Site Cable", "UG Site"),
	("Depth Deviations", "UG Depth Deviation", "UG Site"),
	("Follow-ups with Airtel", "UG Followup Log", "UG Site"),
	("Airtel POs", "Airtel PO", None),
	("Airtel PO Lines", "Airtel PO Line", "Airtel PO"),
	("ROW Applications", "ROW Application", None),
	("Daily Progress", "UG Daily Progress", None),
	("Material Requests", "UG Material Request", None),
	("Material Request Items", "UG Material Request Item", "UG Material Request"),
	("Material Orders", "UG Material Order", None),
	("Material Order Items", "UG Material Order Item", "UG Material Order"),
	("Material Dispatches", "UG Material Dispatch", None),
	("Material Dispatch Items (Cable ID, Readings)", "UG Material Dispatch Item", "UG Material Dispatch"),
	("Punch Points", "UG Punch Point", None),
	("Employees", "UG Employee", None),
	("Vendors", "UG Vendor", None),
	("Splicers", "UG Splicer", None),
	("Zones / Areas", "UG Zone", None),
]
REPORT_PREFIX = "report:"
NUMERIC = ("Int", "Float", "Currency", "Percent")
MAX_ROWS = 50000
PREVIEW_ROWS = 200
FORMATS = {
	"xlsx": ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
	"pdf": ("pdf", "application/pdf"),
	"doc": ("doc", "application/msword"),
	"csv": ("csv", "text/csv"),
}


# ------------------------------------------------------------ what can be reported
@frappe.whitelist()
def get_sources():
	lists = [
		{"value": doctype, "label": _(label)}
		for label, doctype, parent in SOURCES
		if frappe.has_permission(parent or doctype, "read")
	]
	reports = []
	for name in frappe.get_all("Report", {"module": "Underground", "disabled": 0}, pluck="name", order_by="name"):
		if frappe.get_doc("Report", name).is_permitted():
			reports.append({"value": REPORT_PREFIX + name, "label": _(name)})
	return {"lists": lists, "reports": reports}


def resolve(source):
	"""(label, doctype, parent) of a list source, after the read permission check."""
	for label, doctype, parent in SOURCES:
		if doctype == source:
			if not frappe.has_permission(parent or doctype, "read"):
				frappe.throw(_("Not permitted to read {0}.").format(_(parent or doctype)), frappe.PermissionError)
			return label, doctype, parent
	frappe.throw(_("Unknown report source {0}.").format(source))


def parent_title_field(parent):
	meta = frappe.get_meta(parent)
	return meta.title_field if meta.title_field and meta.title_field != "name" else None


@frappe.whitelist()
def get_fields(source):
	"""Columns that can be picked for a list source (a ready report's columns come from running it)."""
	if source.startswith(REPORT_PREFIX):
		return []
	_label, doctype, parent = resolve(source)
	meta = frappe.get_meta(doctype)
	# "default": ticked when the source is picked (ID plus the list-view columns).
	fields = []
	if parent:
		fields.append({"fieldname": "parent", "label": _(parent), "fieldtype": "Link", "options": parent, "default": 1})
		title = parent_title_field(parent)
		if title:
			label = frappe.get_meta(parent).get_label(title)
			fields.append({"fieldname": "parent_title", "label": f"{_(parent)}: {_(label)}", "fieldtype": "Data",
			               "default": 1})
	else:
		fields.append({"fieldname": "name", "label": _("ID"), "fieldtype": "Link", "options": doctype, "default": 1})
	for df in meta.fields:
		if df.fieldtype in no_value_fields or df.fieldtype in table_fields or df.hidden:
			continue
		fields.append({"fieldname": df.fieldname, "label": _(df.label or df.fieldname), "fieldtype": df.fieldtype,
		               "options": df.options, "default": df.in_list_view})
	if not parent:
		fields += [
			{"fieldname": "creation", "label": _("Created On"), "fieldtype": "Datetime"},
			{"fieldname": "modified", "label": _("Last Updated"), "fieldtype": "Datetime"},
		]
	return fields


# ------------------------------------------------------------ fetching rows
def parse(value, default):
	if value in (None, ""):
		return default
	return json.loads(value) if isinstance(value, str) else value


def fetch(source, columns=None, filters=None, order_by=None, sort_order="asc", limit=MAX_ROWS):
	"""(title, columns, rows) — columns as dicts, rows as dicts keyed by fieldname."""
	columns = parse(columns, [])
	filters = parse(filters, [] if not (source or "").startswith(REPORT_PREFIX) else {})
	if source.startswith(REPORT_PREFIX):
		return fetch_report(source[len(REPORT_PREFIX):], columns, filters, order_by, sort_order, limit)

	label, doctype, parent = resolve(source)
	allowed = {f["fieldname"]: f for f in get_fields(source)}
	columns = [c for c in columns if c in allowed] or [f for f in allowed if f not in ("creation", "modified")][:8]
	direction = "desc" if sort_order == "desc" else "asc"
	order = f"`tab{doctype}`.`{order_by}` {direction}" if order_by in allowed and order_by != "parent_title" else None
	query_fields = [c for c in columns if c != "parent_title"]
	if "parent_title" in columns and "parent" not in query_fields:
		query_fields.append("parent")

	if parent:
		parents = frappe.get_list(parent, pluck="name", limit_page_length=0)
		rows = []
		if parents:
			rows = frappe.get_all(
				doctype,
				filters=[*filters, [doctype, "parenttype", "=", parent], [doctype, "parent", "in", parents]],
				fields=query_fields,
				order_by=order or "parent asc, idx asc",
				limit_page_length=limit,
			)
		title = parent_title_field(parent)
		if "parent_title" in columns and title and rows:
			titles = dict(frappe.get_all(parent, {"name": ["in", list({r.parent for r in rows})]}, ["name", title],
			                             as_list=True))
			for row in rows:
				row["parent_title"] = titles.get(row.parent)
	else:
		rows = frappe.get_list(doctype, fields=query_fields, filters=filters, order_by=order or "creation desc",
		                       limit_page_length=limit)
	return _(label), [allowed[c] for c in columns], rows


def fetch_report(report_name, columns, filters, order_by, sort_order, limit):
	from frappe.desk.query_report import run

	report = frappe.get_doc("Report", report_name)
	if report.module != "Underground" or not report.is_permitted():
		frappe.throw(_("Not permitted to run report {0}.").format(report_name), frappe.PermissionError)
	result = run(report_name, filters=filters, ignore_prepared_report=True, are_default_filters=False)
	all_columns = [normalize_column(c) for c in result.get("columns") or []]
	frappe.flags.ug_report_columns = all_columns
	data = result.get("result") or []
	if result.get("add_total_row") and data and isinstance(data[-1], list | tuple):
		data = data[:-1]  # the report's own total row; ours is added on request
	rows = [
		frappe._dict(row) if isinstance(row, dict) else frappe._dict(zip([c["fieldname"] for c in all_columns], row))
		for row in data
	]
	picked = [c for c in all_columns if c["fieldname"] in columns] or all_columns
	if order_by in {c["fieldname"] for c in all_columns}:
		rows.sort(key=lambda r: sort_key(r.get(order_by)), reverse=sort_order == "desc")
	return _(report_name), picked, rows[:limit]


def normalize_column(column):
	if isinstance(column, str):  # "Label:Fieldtype/Options:Width"
		parts = column.split(":")
		fieldtype = (parts[1].split("/")[0] if len(parts) > 1 and parts[1] else "Data") or "Data"
		return {"fieldname": frappe.scrub(parts[0]), "label": parts[0], "fieldtype": fieldtype}
	fieldname = column.get("fieldname") or frappe.scrub(column.get("label") or "")
	return {"fieldname": fieldname, "label": column.get("label") or fieldname,
	        "fieldtype": column.get("fieldtype") or "Data", "options": column.get("options")}


def sort_key(value):
	if value is None or value == "":
		return (0, "")
	if isinstance(value, int | float):
		return (1, value)
	return (2, str(value).lower())


def shape(columns, rows, group_by=None, total_row=False):
	"""Group the rows (count and sums of the number columns) and add a total row if asked."""
	if group_by and group_by in {c["fieldname"] for c in columns}:
		key_col = next(c for c in columns if c["fieldname"] == group_by)
		numeric = [c for c in columns if c["fieldtype"] in NUMERIC and c["fieldname"] != group_by]
		groups = {}
		for row in rows:
			key = row.get(group_by)
			group = groups.setdefault(key, {group_by: key, "_count": 0, **{c["fieldname"]: 0 for c in numeric}})
			group["_count"] += 1
			for c in numeric:
				group[c["fieldname"]] += flt(row.get(c["fieldname"]))
		columns = [key_col, {"fieldname": "_count", "label": _("Count"), "fieldtype": "Int"}] + [
			{**c, "label": _("Total {0}").format(c["label"])} for c in numeric
		]
		rows = sorted(groups.values(), key=lambda g: sort_key(g[group_by]))
	if total_row and rows:
		total = {c["fieldname"]: sum(flt(r.get(c["fieldname"])) for r in rows) for c in columns if c["fieldtype"] in NUMERIC}
		first = columns[0]["fieldname"]
		total[first] = _("Total") if columns[0]["fieldtype"] not in NUMERIC else total.get(first)
		rows = [*rows, {**total, "_is_total": 1}]
	return columns, rows


def display(value, column):
	"""The value as text for PDF, Word and CSV."""
	if value is None or value == "":
		return ""
	if value == _("Total"):  # the total row's label, whatever the first column's type
		return value
	fieldtype = column.get("fieldtype")
	if fieldtype == "Check":
		return _("Yes") if cint(value) else _("No")
	if fieldtype == "Date":
		return formatdate(value)
	if fieldtype == "Datetime":
		return format_datetime(value)
	if fieldtype == "Currency":
		return fmt_money(value, precision=2)
	if fieldtype == "Float":
		return fmt_money(value, precision=3).rstrip("0").rstrip(".")
	if fieldtype == "Int":
		return str(cint(value)) if isinstance(value, int | float) else str(value)
	if fieldtype in ("Small Text", "Text", "Long Text", "Text Editor", "HTML Editor"):
		return strip_html(str(value)).strip()
	return str(value)


def describe_filters(source, filters):
	"""Readable filter lines for the top of the PDF / Word file."""
	filters = parse(filters, {})
	if source.startswith(REPORT_PREFIX):
		return [f"{frappe.unscrub(k)}: {v}" for k, v in (filters or {}).items() if v not in (None, "", 0)]
	_label, doctype, _parent = resolve(source)
	lines = []
	for f in filters or []:
		dt, field, op, value = (f + [None] * 4)[:4] if isinstance(f, list) else (None, None, None, None)
		if not field:
			continue
		label = frappe.get_meta(dt or doctype).get_label(field)
		value = ", ".join(map(str, value)) if isinstance(value, list) else value
		lines.append(f"{_(label)} {op} {value}")
	return lines


# ------------------------------------------------------------ preview and download
@frappe.whitelist()
def preview(source, columns=None, filters=None, order_by=None, sort_order="asc", group_by=None, total_row=0):
	title, cols, rows = fetch(source, columns, filters, order_by, sort_order)
	cols, rows = shape(cols, rows, group_by, cint(total_row))
	return {
		"title": title,
		"columns": cols,
		"rows": [[display(r.get(c["fieldname"]), c) for c in cols] for r in rows[:PREVIEW_ROWS]],
		"total": len(rows),
		"numeric": [c["fieldtype"] in NUMERIC for c in cols],
		"available": frappe.flags.get("ug_report_columns"),
	}


@frappe.whitelist()
def download(source, fmt="xlsx", columns=None, filters=None, order_by=None, sort_order="asc", group_by=None,
             total_row=0, title=None):
	if fmt not in FORMATS:
		frappe.throw(_("Unknown file format {0}.").format(fmt))
	default_title, cols, rows = fetch(source, columns, filters, order_by, sort_order)
	cols, rows = shape(cols, rows, group_by, cint(total_row))
	title = (title or "").strip() or default_title
	stamp = now_datetime()
	subtitle = [
		_("Generated on {0} by {1}").format(format_datetime(stamp), frappe.utils.get_fullname()),
		_("Rows: {0}").format(len([r for r in rows if not r.get("_is_total")])),
		*[_("Filter: {0}").format(line) for line in describe_filters(source, filters)],
	]
	if group_by:
		subtitle.append(_("Grouped by {0}").format(cols[0]["label"]))
	headers = [c["label"] for c in cols]
	numeric = [c["fieldtype"] in NUMERIC for c in cols]
	text_rows = [[display(r.get(c["fieldname"]), c) for c in cols] for r in rows]

	if fmt == "xlsx":
		content = make_xlsx(title, headers, cols, rows)
	elif fmt == "csv":
		buffer = io.StringIO()
		writer = csv.writer(buffer)
		writer.writerow(headers)
		writer.writerows(text_rows)
		content = buffer.getvalue().encode("utf-8-sig")
	elif fmt == "pdf":
		content = make_pdf(title, subtitle, headers, text_rows, numeric)
	else:
		content = make_word(title, subtitle, headers, text_rows, numeric).encode("utf-8")

	extension, _content_type = FORMATS[fmt]
	safe = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_") or "report"
	frappe.response.filename = f"{safe}_{stamp.strftime('%Y%m%d_%H%M')}.{extension}"
	frappe.response.filecontent = content
	frappe.response.type = "download"


def make_xlsx(title, headers, cols, rows):
	from frappe.utils.xlsxutils import make_xlsx as frappe_xlsx

	data = [headers]
	for row in rows:
		line = []
		for c in cols:
			value = row.get(c["fieldname"])
			if c["fieldtype"] in NUMERIC and value not in (None, "") and not isinstance(value, str):
				line.append(flt(value))
			else:
				line.append(display(value, c))
		data.append(line)
	sheet = re.sub(r"[\[\]:*?/\\]+", " ", title).strip()[:31] or "Report"  # characters Excel refuses
	return frappe_xlsx(data, sheet).getvalue()


def table_html(headers, rows, numeric):
	head = "".join(f"<th>{frappe.utils.escape_html(h)}</th>" for h in headers)
	body = "".join(
		"<tr>" + "".join(
			f'<td{" class=num" if is_num else ""}>{frappe.utils.escape_html(v)}</td>' for v, is_num in zip(row, numeric)
		) + "</tr>"
		for row in rows
	)
	return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


TABLE_CSS = """
body { font-family: Arial, Helvetica, sans-serif; font-size: 8pt; color: #1f2933; }
h1 { font-size: 14pt; color: #1D4E89; margin: 0 0 4pt; }
p.sub { color: #555; margin: 0 0 2pt; font-size: 8pt; }
table { border-collapse: collapse; width: 100%; margin-top: 8pt; }
th { background: #1D4E89; color: #fff; text-align: left; padding: 3pt 4pt; border: 0.5pt solid #1D4E89; }
td { padding: 3pt 4pt; border: 0.5pt solid #c8ccd4; vertical-align: top; }
tr:nth-child(even) td { background: #f2f5f9; }
td.num { text-align: right; }
thead { display: table-header-group; }
"""


def make_pdf(title, subtitle, headers, rows, numeric):
	"""WeasyPrint when the server has it working; otherwise the built-in table writer."""
	orientation = "landscape" if len(headers) > 6 else "portrait"
	try:
		from weasyprint import HTML

		size = "A4 landscape" if orientation == "landscape" else "A4"
		html = (
			f"<html><head><meta charset='utf-8'><style>@page {{ size: {size}; margin: 12mm; "
			f"@bottom-right {{ content: 'Page ' counter(page) ' of ' counter(pages); font-size: 7pt; color: #777; }} }}"
			f"{TABLE_CSS}</style></head><body><h1>{frappe.utils.escape_html(title)}</h1>"
			+ "".join(f"<p class='sub'>{frappe.utils.escape_html(s)}</p>" for s in subtitle)
			+ table_html(headers, rows, numeric) + "</body></html>"
		)
		return HTML(string=html).write_pdf()
	except Exception:
		from underground.pdf_table import make_pdf as table_pdf

		return table_pdf(title, subtitle, headers, rows, ["right" if n else "left" for n in numeric], orientation,
		                 footer=title)


def make_word(title, subtitle, headers, rows, numeric):
	"""An HTML document Word opens as a .doc, landscape when the table is wide."""
	landscape = len(headers) > 6
	page = "size: 841.9pt 595.3pt; mso-page-orientation: landscape;" if landscape else "size: 595.3pt 841.9pt;"
	return (
		"<html xmlns:o='urn:schemas-microsoft-com:office:office' xmlns:w='urn:schemas-microsoft-com:office:word' "
		"xmlns='http://www.w3.org/TR/REC-html40'><head><meta charset='utf-8'>"
		f"<title>{frappe.utils.escape_html(title)}</title><style>@page Section1 {{ {page} margin: 36pt; }} "
		f"div.Section1 {{ page: Section1; }} {TABLE_CSS}</style></head><body><div class='Section1'>"
		f"<h1>{frappe.utils.escape_html(title)}</h1>"
		+ "".join(f"<p class='sub'>{frappe.utils.escape_html(s)}</p>" for s in subtitle)
		+ table_html(headers, rows, numeric) + "</div></body></html>"
	)


# ------------------------------------------------------------ saved reports
@frappe.whitelist()
def get_templates():
	"""The user's own saved reports and everyone's public ones."""
	return frappe.get_all(
		"UG Report Template",
		filters=[["owner", "=", frappe.session.user]],
		fields=["name", "template_name", "source", "config", "is_public", "owner"],
		order_by="template_name asc",
	) + frappe.get_all(
		"UG Report Template",
		filters=[["is_public", "=", 1], ["owner", "!=", frappe.session.user]],
		fields=["name", "template_name", "source", "config", "is_public", "owner"],
		order_by="template_name asc",
	)


@frappe.whitelist()
def save_template(template_name, source, config, is_public=0, name=None):
	template_name = (template_name or "").strip()
	if not template_name:
		frappe.throw(_("Give the report a name."))
	if source.startswith(REPORT_PREFIX):
		if not frappe.get_doc("Report", source[len(REPORT_PREFIX):]).is_permitted():
			frappe.throw(_("Not permitted."), frappe.PermissionError)
	else:
		resolve(source)
	values = {"template_name": template_name, "source": source,
	          "config": config if isinstance(config, str) else json.dumps(config), "is_public": cint(is_public)}
	if name and frappe.db.exists("UG Report Template", name):
		doc = frappe.get_doc("UG Report Template", name)
		doc.check_permission("write")
		doc.update(values)
		doc.save()
	else:
		doc = frappe.get_doc({"doctype": "UG Report Template", **values}).insert()
	return doc.name


@frappe.whitelist()
def delete_template(name):
	frappe.delete_doc("UG Report Template", name)
