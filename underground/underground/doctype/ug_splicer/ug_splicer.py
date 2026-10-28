# Copyright (c) 2026, huda and contributors
"""UG Splicer — a splicer of a vendor (or freelance). A vendor's own login adds and sees only its
own splicers."""

import frappe
from frappe import _
from frappe.model.document import Document


class UGSplicer(Document):
	def validate(self):
		from underground.permission import vendor_only

		vendor = vendor_only(frappe.session.user)
		if vendor == "":
			frappe.throw(_("Your login is not linked to a UG Vendor (ERP User on the vendor). Ask the Back Office."))
		if vendor:
			self.vendor = vendor
