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
# Points on Airtel's side of the route: chambers, handholes, cut points, POPs and network elements
# such as 'PUN/LGM/901'.
TAPPING_RE = re.compile(
	r"joint|chamber|tap|splice|manhole|handhole|closure|cut\s*point|\bpop\b|\brfs\b|peyto|\bjc\b|\btp\b|\bhh\d*\b"
	r"|\b[a-z]{3}/[a-z]{3}/\d{3}\b",
	re.I,
)


def parse_kmz(content, file_name="", node_id=None):
	"""Site, tapping point and route of one node. `node_id` (the site's own node, when known) picks
	that node out of a route KMZ that maps several nodes."""
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

	nodes = node_ids(points)
	node_id = (node_id or "").strip().upper() or guess_node_id(points, file_name)
	existing = [line for line in lines if re.search(r"exist", line["name"] or "", re.I)]
	site = pick_site_point(points, node_id)
	candidates = [line for line in lines if line not in existing]
	own = [line for line in candidates if node_id and node_id in (line["name"] or "").upper()]
	if len(nodes) > 1 and not own and site and candidates:
		# Route KMZ whose spur to this node is not named after it: the line that ends at the site.
		own = [min(candidates, key=lambda line: min(end_distance(site, line)))]
	if len(nodes) > 1 and own:
		proposed = own
	else:
		proposed = [line for line in lines if re.search(r"propos", line["name"] or "", re.I)] or candidates

	if not site and proposed:
		# Only a route drawn: it runs from the tapping point to the site.
		coords = max(proposed, key=lambda line: line["length"])["coords"]
		site = {"name": "Route end", "lon": coords[-1][0], "lat": coords[-1][1]}
		points.append(site)
		points.append({"name": "Route start (tapping)", "lon": coords[0][0], "lat": coords[0][1]})
	others = [p for p in points if p is not site]
	taps = [p for p in others if TAPPING_RE.search(p["name"] or "")] or others
	tapping = min(taps, key=lambda p: distance(site, p)) if site and taps else None

	return {
		"node_id": node_id,
		"nodes": nodes,
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


def end_distance(point, line):
	"""Distances from a point to the two ends of a line."""
	(x1, y1), (x2, y2) = line["coords"][0], line["coords"][-1]
	return haversine(point["lon"], point["lat"], x1, y1), haversine(point["lon"], point["lat"], x2, y2)


def node_ids(points):
	"""Node IDs of the site points, in file order (a route KMZ maps several)."""
	found = []
	for point in points:
		match = NODE_RE.search((point["name"] or "").upper())
		if match and not TAPPING_RE.search(point["name"]) and match.group(1) not in found:
			found.append(match.group(1))
	return found


def guess_node_id(points, file_name):
	"""The node the file is named after when it is in the file too, else the first node point."""
	nodes = node_ids(points)
	match = NODE_RE.search(re.split(r"[\\/]", file_name)[-1].upper())
	if match and (match.group(1) in nodes or not nodes):
		return match.group(1)
	return nodes[0] if nodes else None


def pick_site_point(points, node_id):
	if node_id:
		named = [p for p in points if node_id in (p["name"] or "").upper()]
		site = next((p for p in named if not TAPPING_RE.search(p["name"] or "")), named[0] if named else None)
		if site:
			return site
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
