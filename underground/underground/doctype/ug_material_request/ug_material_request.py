# Copyright (c) 2026, huda and contributors
"""UG Material Request — material a site needs, asked for by its Area Manager once they have
approved the site. Draft → Requested (Material Team told) → Ordered (a Material Order carries it)
→ Dispatched (material dispatched to the site); the Material Team can reject it with a reason."""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.query_builder.functions import Sum
from frappe.utils import cint, flt, get_url_to_form, today

from underground.utils import get_role_users, get_setting

EDITABLE = ("Draft", "Rejected")


class UGMaterialRequest(Document):
	def validate(self):
		site = frappe.db.get_value(
			"UG Site", self.ug_site, ["area_manager", "am_approval_status", "is_mobilization"], as_dict=True
		)
		if site.is_mobilization:
			frappe.throw(_("{0} is a Mobilization (MO) site; it has no material.").format(self.ug_site))
		if site.area_manager and site.am_approval_status not in ("In Progress", "Closed"):
			frappe.throw(
				_("Area Manager {0} has not approved site {1} yet; material is requested after the approval.").format(
					site.area_manager, self.ug_site),
				title=_("Site Not Approved"),
			)
		if self.is_new():
			self.status = "Draft"


@frappe.whitelist()
def get_default_items(site):
	"""Starting rows from the site's PO: duct for the civil length, cable for the optical length."""
	lengths = frappe.db.get_value("UG Site", site, ["po_civil_length", "po_optical_length"], as_dict=True) or {}
	rows = []
	for group, length in (("Duct", lengths.get("po_civil_length")), ("Cable", lengths.get("po_optical_length"))):
		item = frappe.db.get_value("UG Material Item", {"item_group": group}, "name", order_by="creation asc")
		if item and flt(length):
			rows.append({"item": item, "qty": flt(length), "uom": frappe.db.get_value("UG Material Item", item, "uom")})
	return rows


@frappe.whitelist()
def send_request(name):
	"""Send the request to the Material Team."""
	doc = frappe.get_doc("UG Material Request", name)
	doc.check_permission("write")
	if doc.status not in EDITABLE:
		frappe.throw(_("This request is already {0}.").format(_(doc.status)))
	doc.update({"status": "Requested", "requested_by": frappe.session.user, "requested_on": today(),
	            "rejection_reason": None})
	doc.save()
	label = doc.node_id or doc.ug_site
	items = ", ".join(f"{row.item} {flt(row.qty):g} {row.uom or ''}".strip() for row in doc.items)
	notify(doc, get_role_users("UG Material Team", "UG Back Office"),
	       _("Material requested for site {0}").format(label),
	       _("{0} requested material for site {1}: {2}.").format(frappe.utils.get_fullname(), label, items))
	return doc.status


@frappe.whitelist()
def reject_request(name, reason):
	"""The Material Team sends the request back with a reason."""
	if not {"UG Material Team", "UG Admin", "System Manager"} & set(frappe.get_roles()):
		frappe.throw(_("Only the Material Team can reject a material request."), frappe.PermissionError)
	reason = (reason or "").strip()
	if not reason:
		frappe.throw(_("Give the reason for rejecting."))
	doc = frappe.get_doc("UG Material Request", name)
	if doc.status != "Requested":
		frappe.throw(_("Only a Requested material request can be rejected."))
	doc.db_set({"status": "Rejected", "rejection_reason": reason})
	label = doc.node_id or doc.ug_site
	notify(doc, [doc.requested_by, doc.am_user], _("Material request for site {0} rejected").format(label),
	       _("Reason: {0}").format(frappe.utils.escape_html(reason)))
	return doc.status


def notify(doc, users, subject, note):
	message = f'<p>{note}</p><p><a href="{get_url_to_form(doc.doctype, doc.name)}">{_("Open the request")}</a></p>'
	send_emails = cint(get_setting("send_emails"))
	for user in set(filter(None, users)) - {frappe.session.user}:
		frappe.get_doc(
			{
				"doctype": "Notification Log",
				"for_user": user,
				"type": "Alert",
				"document_type": doc.doctype,
				"document_name": doc.name,
				"subject": subject[:140],
				"email_content": message,
			}
		).insert(ignore_permissions=True)
		email = frappe.db.get_value("User", user, "email")
		if send_emails and email:
			frappe.sendmail(recipients=[email], subject=subject[:140], message=message,
			                reference_doctype=doc.doctype, reference_name=doc.name)


def update_from_orders(requests):
	"""Ordered quantity and status of the requests named on Material Order lines."""
	order_item = frappe.qb.DocType("UG Material Order Item")
	for name in set(filter(None, requests)):
		if not frappe.db.exists("UG Material Request", name):
			continue
		rows = (
			frappe.qb.from_(order_item)
			.select(order_item.item, Sum(order_item.ordered_qty), order_item.parent)
			.where((order_item.material_request == name) & (order_item.parenttype == "UG Material Order"))
			.groupby(order_item.item, order_item.parent)
			.orderby(order_item.parent)
			.run()
		)
		ordered, last_order = {}, None
		for item, qty, order in rows:
			ordered[item] = ordered.get(item, 0) + flt(qty)
			last_order = order
		doc = frappe.get_doc("UG Material Request", name)
		for row in doc.items:
			row.ordered_qty = ordered.get(row.item, 0)
			row.db_update()
		status = doc.status
		if ordered and status in ("Requested", "Ordered"):
			status = "Ordered"
		elif not ordered and status == "Ordered":
			status = "Requested"
		doc.db_set({"status": status, "material_order": last_order})


def mark_dispatched(sites):
	"""Ordered requests of the sites that have now had material dispatched."""
	for site in set(filter(None, sites)):
		if frappe.db.get_value("UG Site", site, "material_dispatched"):
			for name in frappe.get_all("UG Material Request", {"ug_site": site, "status": "Ordered"}, pluck="name"):
				frappe.db.set_value("UG Material Request", name, "status", "Dispatched")
