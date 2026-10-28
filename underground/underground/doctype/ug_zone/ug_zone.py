# Copyright (c) 2026, huda and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt

from underground.kmz_reader import haversine, parse_boundary, point_in_rings, ring_center


class UGZone(Document):
	def validate(self):
		if not self.boundary_kmz:
			self.boundary, self.has_boundary = None, 0
			return
		if self.boundary and not self.has_value_changed("boundary_kmz"):
			return
		file_doc = frappe.get_doc("File", {"file_url": self.boundary_kmz})
		try:
			rings = parse_boundary(file_doc.get_content(), file_doc.file_name or self.boundary_kmz)
		except Exception:
			frappe.log_error(title="UG Zone: could not read boundary KMZ")
			rings = []
		if not rings:
			frappe.throw(_("No polygon was found in this KMZ. Draw the area with Google Earth's Add Polygon."))
		self.boundary, self.has_boundary = json.dumps(rings), 1
		if not (self.center_latitude and self.center_longitude):
			self.center_latitude, self.center_longitude = ring_center(rings)


def find_zone(lat, lon):
	"""The area a location falls in: inside a boundary first, else the nearest area centre
	within its coverage radius. Returns (zone, how) or (None, None)."""
	zones = frappe.get_all(
		"UG Zone",
		fields=["name", "boundary", "center_latitude", "center_longitude", "coverage_km"],
	)
	for zone in zones:
		if zone.boundary and point_in_rings(lat, lon, json.loads(zone.boundary)):
			return zone.name, _("inside the area boundary")
	nearest, nearest_km = None, None
	for zone in zones:
		if not (zone.center_latitude and zone.center_longitude):
			continue
		km = haversine(lon, lat, zone.center_longitude, zone.center_latitude) / 1000
		if flt(zone.coverage_km) and km > flt(zone.coverage_km):
			continue
		if nearest_km is None or km < nearest_km:
			nearest, nearest_km = zone.name, km
	if nearest:
		return nearest, _("nearest area centre, {0} km").format(round(nearest_km, 1))
	return None, None
