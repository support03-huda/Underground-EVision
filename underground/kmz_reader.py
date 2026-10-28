# Copyright (c) 2026, huda and contributors
"""Reads an Airtel site KMZ: site location, tapping point and route lengths.

A typical file (e.g. ANE3692_MH.kmz) holds one folder with:
- a Point named after the node (the site),
- a Point for the tapping point (joint chamber on the existing route),
- a LineString "<node> Proposed OFC Route" (the route to be built),
- a LineString "... Existing OFC Route" (route already in the ground).
"""

import io
import json
import math
import re
import zipfile
import xml.etree.ElementTree as ET

MAX_KML_SIZE = 20 * 1024 * 1024
NODE_RE = re.compile(r"\b([A-Z]{2,4}\d{3,5})\b")
TAPPING_RE = re.compile(r"joint|chamber|tap|splice|manhole|\bjc\b|\btp\b|\bhh\b", re.I)


def parse_kmz(content, file_name=""):
	kml = read_kml(content, file_name)
	points, lines = [], []
	for placemark in ET.fromstring(kml).iter():
		if tag(placemark) != "Placemark":
			continue
		name = child_text(placemark, "name")
		for geom in placemark.iter():
			kind = tag(geom)
			if kind not in ("Point", "LineString"):
				continue
			coords = parse_coords(next((c.text for c in geom.iter() if tag(c) == "coordinates"), ""))
			if kind == "Point" and coords:
				points.append({"name": name, "lon": coords[0][0], "lat": coords[0][1]})
			elif kind == "LineString" and len(coords) > 1:
				lines.append({"name": name, "coords": coords, "length": line_length(coords)})

	node_id = guess_node_id(points, file_name)
	site = pick_site_point(points, node_id)
	tapping = next((p for p in points if p is not site and TAPPING_RE.search(p["name"] or "")), None)
	if not tapping:
		tapping = next((p for p in points if p is not site), None)
	existing = [line for line in lines if re.search(r"exist", line["name"] or "", re.I)]
	proposed = [line for line in lines if re.search(r"propos", line["name"] or "", re.I)]
	if not proposed:
		proposed = [line for line in lines if line not in existing]

	return {
		"node_id": node_id,
		"latitude": site and round(site["lat"], 6),
		"longitude": site and round(site["lon"], 6),
		"tapping_point": tapping and f"{tapping['name']} ({tapping['lat']:.6f}, {tapping['lon']:.6f})",
		"tapping_distance": tapping and site and round(distance(site, tapping), 1),
		"proposed_length": round(sum(line["length"] for line in proposed), 1),
		"existing_length": round(sum(line["length"] for line in existing), 1),
		"route_count": len(proposed),
		"map": json.dumps(to_geojson(points, lines, proposed, site, tapping)),
	}


def parse_boundary(content, file_name=""):
	"""Outer rings of every Polygon in an area boundary KMZ, as [[lon, lat], ...] lists."""
	rings = []
	for polygon in ET.fromstring(read_kml(content, file_name)).iter():
		if tag(polygon) != "Polygon":
			continue
		outer = next((b for b in polygon if tag(b) == "outerBoundaryIs"), polygon)
		coords = parse_coords(next((c.text for c in outer.iter() if tag(c) == "coordinates"), ""))
		if len(coords) >= 3:
			rings.append([[round(x, 7), round(y, 7)] for x, y in coords])
	return rings


def ring_center(rings):
	points = [p for ring in rings for p in ring]
	return sum(p[1] for p in points) / len(points), sum(p[0] for p in points) / len(points)


def point_in_rings(lat, lon, rings):
	"""Ray casting: is (lat, lon) inside any of the rings?"""
	for ring in rings:
		inside = False
		j = len(ring) - 1
		for i in range(len(ring)):
			xi, yi = ring[i]
			xj, yj = ring[j]
			if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
				inside = not inside
			j = i
		if inside:
			return True
	return False


def read_kml(content, file_name):
	if content[:2] == b"PK":
		with zipfile.ZipFile(io.BytesIO(content)) as kmz:
			names = [i for i in kmz.infolist() if i.filename.lower().endswith(".kml")]
			if not names:
				raise ValueError("No KML inside the KMZ")
			info = next((i for i in names if i.filename.lower() == "doc.kml"), names[0])
			if info.file_size > MAX_KML_SIZE:
				raise ValueError("KML is too large")
			return kmz.read(info)
	if file_name.lower().endswith(".kml") or content.lstrip()[:5] == b"<?xml":
		return content
	raise ValueError("Not a KMZ / KML file")


def tag(el):
	return el.tag.rsplit("}", 1)[-1] if isinstance(el.tag, str) else ""


def child_text(el, name):
	return next((" ".join((c.text or "").split()) for c in el if tag(c) == name), "")


def parse_coords(text):
	coords = []
	for part in (text or "").split():
		values = part.split(",")
		if len(values) >= 2:
			try:
				coords.append((float(values[0]), float(values[1])))
			except ValueError:
				pass
	return coords


def haversine(lon1, lat1, lon2, lat2):
	lon1, lat1, lon2, lat2 = map(math.radians, (lon1, lat1, lon2, lat2))
	h = math.sin((lat2 - lat1) / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
	return 2 * 6371008.8 * math.asin(math.sqrt(h))


def line_length(coords):
	return sum(haversine(*coords[i], *coords[i + 1]) for i in range(len(coords) - 1))


def distance(a, b):
	return haversine(a["lon"], a["lat"], b["lon"], b["lat"])


def guess_node_id(points, file_name):
	for point in points:
		match = NODE_RE.search((point["name"] or "").upper())
		if match and not TAPPING_RE.search(point["name"]):
			return match.group(1)
	match = NODE_RE.search(re.split(r"[\\/]", file_name)[-1].upper())
	return match.group(1) if match else None


def pick_site_point(points, node_id):
	if node_id:
		for point in points:
			if node_id in (point["name"] or "").upper():
				return point
	return next((p for p in points if not TAPPING_RE.search(p["name"] or "")), points[0] if points else None)


def to_geojson(points, lines, proposed, site, tapping):
	features = [
		{
			"type": "Feature",
			"properties": {
				"name": p["name"],
				"kind": "Site" if p is site else "Tapping Point" if p is tapping else "Point",
			},
			"geometry": {"type": "Point", "coordinates": [round(p["lon"], 7), round(p["lat"], 7)]},
		}
		for p in points
	]
	features += [
		{
			"type": "Feature",
			"properties": {
				"name": f"{line['name']} ({line['length']:.0f} m)",
				"route": "Proposed" if line in proposed else "Existing",
			},
			"geometry": {"type": "LineString", "coordinates": [[round(x, 7), round(y, 7)] for x, y in line["coords"]]},
		}
		for line in lines
	]
	return {"type": "FeatureCollection", "features": features}
