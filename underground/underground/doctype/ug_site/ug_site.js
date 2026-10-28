// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("UG Site", {
	setup(frm) {
		frm.set_query("district", () => ({ filters: frm.doc.zone ? { zone: frm.doc.zone } : {} }));
		frm.set_query("route", () => ({ filters: frm.doc.district ? { district: frm.doc.district } : {} }));
		frm.set_query("project_manager", () => ({ filters: { is_active: 1 } }));
		// Only the Area Managers of the site's area.
		frm.set_query("area_manager", () => ({
			filters: Object.assign({ is_active: 1, designation: "Area Manager" }, frm.doc.zone ? { zone: frm.doc.zone } : {}),
		}));
		frm.set_query("execution_spoc", () => ({ filters: { is_active: 1 } }));
		frm.set_query("team_vendor", () => ({ filters: { is_active: 1 } }));
		frm.set_query("execution_vendor", () => ({ filters: { is_active: 1 } }));
		frm.set_query("splicing_vendor", () => ({ filters: { is_active: 1 } }));
		// Only the splicers of the site's splicing vendor (or freelance ones when there is no vendor).
		frm.set_query("splicer", () => ({
			filters: Object.assign({ is_active: 1 }, frm.doc.splicing_vendor ? { vendor: frm.doc.splicing_vendor } : {}),
		}));
		frm.set_query("item", "cable_logs", () => ({ filters: { item_group: "Cable" } }));
	},

	refresh(frm) {
		show_indicators(frm);
		render_kmz_map(frm);
		add_approval_buttons(frm);
		if (frm.is_new() || frm.doc.is_mobilization) return;

		if (frm.doc.row_required === "Yes" && (frm.doc.row_authorities || []).some((r) => !r.row_application)) {
			frm.add_custom_button(__("Create ROW Applications"), () => {
				frappe.call({
					method: "underground.underground.doctype.ug_site.ug_site.create_row_applications",
					args: { site: frm.doc.name },
					freeze: true,
				}).then((r) => {
					frappe.show_alert({
						message: __("{0} ROW Application(s) created", [(r.message || []).length]),
						indicator: "green",
					});
					frm.reload_doc();
				});
			}, __("Create"));
		}
		if (frm.doc.execution_release_date) {
			frm.add_custom_button(__("Daily Progress"), () => {
				frappe.new_doc("UG Daily Progress", { ug_site: frm.doc.name });
			}, __("Create"));
		}
		if (["In Progress", "Closed"].includes(frm.doc.am_approval_status)) {
			frm.add_custom_button(__("Material Request"), () =>
				frappe.new_doc("UG Material Request", { ug_site: frm.doc.name }), __("Create"));
		}
		if (frm.doc.vlc_code) {
			frm.add_custom_button(__("Material Order"), () => {
				frappe.model.with_doctype("UG Material Order", () => {
					const order = frappe.model.get_new_doc("UG Material Order");
					const row = frappe.model.add_child(order, "items");
					row.ug_site = frm.doc.name;
					row.node_id = frm.doc.node_id;
					frappe.set_route("Form", "UG Material Order", order.name);
				});
			}, __("Create"));
		}
		frm.add_custom_button(__("Punch Points from List"), () => add_punch_points(frm), __("Create"));
	},

	splicing_vendor(frm) {
		if (frm.doc.splicer) frm.set_value("splicer", null);
	},

	work_type(frm) {
		if (frm.doc.work_type !== "LM") frm.set_value("ibd_included", 0);
	},

	po_copy(frm) {
		if (!(frm.doc.po_copy || "").toLowerCase().endsWith(".pdf")) return;
		// The Attach field saves the form right after upload. A saved site fills after that save
		// (or the save overwrites it); a new one skips it (it would only list empty mandatory fields).
		if (frm.is_new()) {
			frm._skip_upload_save = true;
			fill_from_po(frm);
		} else frm._fill_po_after_save = true;
	},

	validate(frm) {
		if (frm._skip_upload_save) {
			frm._skip_upload_save = false;
			frappe.validated = false;
		}
	},

	after_save(frm) {
		if (frm._fill_po_after_save) {
			frm._fill_po_after_save = false;
			fill_from_po(frm);
		}
	},

	kmz_file(frm) {
		// A saved site reads the KMZ on the server, in the save the Attach field triggers.
		if (frm.is_new() && /\.km[lz]$/i.test(frm.doc.kmz_file || "")) {
			frm._skip_upload_save = true;
			fill_from_kmz(frm);
		}
	},

	zone(frm) {
		// A new area needs its own Area Manager: the system picks one on save, or pick by hand.
		frm.set_value({ district: null, area_manager: null });
	},

	survey_length(frm) {
		if (frm.doc.survey_length > (frm.doc.po_civil_length || 0) && frm.doc.po_civil_length) {
			frappe.show_alert({
				message: __("Survey length is more than the PO civil length: a length extension is required."),
				indicator: "orange",
			});
		}
	},
});

frappe.ui.form.on("UG PO Line", {
	qty: set_line_amount,
	rate: set_line_amount,
});

function set_line_amount(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "amount", flt(row.qty) * flt(row.rate));
}

function show_indicators(frm) {
	const d = frm.doc;
	if (frm.is_new()) return;
	const flags = [];
	if (d.stage_overdue) flags.push([__("Stage overdue"), "red"]);
	if (d.kmz_overdue) flags.push([__("KMZ overdue"), "red"]);
	if (d.length_extension_required && d.length_extension_status === "Not Required")
		flags.push([__("Length extension needed"), "orange"]);
	if (d.billing_ready && d.billing_status === "Pending") flags.push([__("Billing ready"), "green"]);
	if (d.open_pp) flags.push([__("{0} open punch points", [d.open_pp]), "orange"]);
	APPROVALS.forEach(({ kind, prefix }) => {
		const status = d[`${prefix}_approval_status`];
		if (status === "Pending") flags.push([__("{0} approval pending", [__(kind)]), "orange"]);
		if (status === "In Progress") flags.push([__("{0}: in progress", [__(kind)]), "blue"]);
		if (status === "Rejected") flags.push([__("Rejected by {0}", [__(kind)]), "red"]);
	});
	flags.forEach(([label, color]) => frm.dashboard.add_indicator(label, color));
	if (d.current_stage) {
		frm.page.set_indicator(
			`${d.current_stage} · ${__("Day {0}", [d.site_ageing || 0])}`,
			d.final_ug_status === "Completed" ? "green" : d.stage_overdue ? "red" : "blue"
		);
	}
}

function fill_from_po(frm) {
	frappe.call({
		method: "underground.underground.doctype.ug_site.ug_site.read_po_copy",
		args: { file_url: frm.doc.po_copy, site: frm.is_new() ? null : frm.doc.name },
		freeze: true,
		freeze_message: __("Reading PO..."),
	}).then(({ message: po }) => {
		if (!po) return;
		if (po.existing_site) {
			frappe.msgprint({
				title: __("Node already has a site"),
				indicator: "orange",
				message: __("Node {0} is already on site {1}. Add this PO there (or through Airtel PO) instead of a new site.", [
					po.node_id, `<a href="/app/ug-site/${po.existing_site}">${po.existing_site}</a>`,
				]),
			});
			return;
		}
		const set = {};
		const fill = (field, value) => {
			if (value !== null && value !== undefined && value !== "" && !frm.doc[field]) set[field] = value;
		};
		set.po_number = po.po_number;
		fill("po_receipt_date", frappe.datetime.get_today());
		fill("po_start_date", po.po_start_date);
		fill("po_end_date", po.po_end_date);
		fill("node_id", po.node_id);
		fill("cwip_id", po.cwip_id);
		fill("work_type", po.work_type);
		frm.set_value(set).then(() => {
			if (po.ibd_included && frm.doc.work_type === "LM") frm.set_value("ibd_included", 1);
			// A new site takes the PO's lines; an existing site keeps its earlier PO lines (history).
			if (frm.is_new()) frm.clear_table("po_lines");
			const po_name = po.po_lines[0] && po.po_lines[0].airtel_po;
			if (!(po_name && (frm.doc.po_lines || []).some((row) => row.airtel_po === po_name))) {
				po.po_lines.forEach((line) =>
					Object.assign(frm.add_child("po_lines"), line, { amount: flt(line.qty) * flt(line.rate) })
				);
			}
			frm.refresh_field("po_lines");
			const missing = ["work_type", "zone"].filter((f) => !frm.doc[f]).map((f) => __(frappe.meta.get_label(frm.doctype, f)));
			frappe.show_alert({
				message: __("Filled from PO {0} ({1}): {2} line(s), node {3}.", [
					po.po_number, po.po_type, po.po_lines.length, po.node_id || "?",
				]) + (missing.length ? " " + __("Still to fill: {0}", [missing.join(", ")]) : "")
					+ (po.work_type ? " " + __("Check the Work Type ({0}) and Receipt Date.", [po.work_type]) : ""),
				indicator: missing.length ? "orange" : "green",
			}, 10);
		});
	});
}

function fill_from_kmz(frm) {
	frappe.call({
		method: "underground.underground.doctype.ug_site.ug_site.read_kmz",
		args: { file_url: frm.doc.kmz_file, site: frm.is_new() ? null : frm.doc.name },
		freeze: true,
		freeze_message: __("Reading KMZ..."),
	}).then(({ message: kmz }) => {
		if (!kmz) return;
		const notes = [];
		if (kmz.node_id && frm.doc.node_id && kmz.node_id !== frm.doc.node_id) {
			notes.push(__("This KMZ is for node {0}, but the site is node {1}. Check the file.", [kmz.node_id, frm.doc.node_id]));
		}
		const set = {
			kmz_latitude: kmz.latitude,
			kmz_longitude: kmz.longitude,
			kmz_tapping_point: kmz.tapping_point,
			kmz_tapping_distance: kmz.tapping_distance,
			kmz_route_length: kmz.proposed_length,
			kmz_existing_route_length: kmz.existing_length,
			kmz_map: kmz.map,
			kmz_received: 1,
		};
		if (!frm.doc.node_id && kmz.node_id) set.node_id = kmz.node_id;
		if (!frm.doc.kmz_received_date) set.kmz_received_date = frappe.datetime.get_today();
		frm.set_value(set).then(() => {
			render_kmz_map(frm);
			const po_length = flt(frm.doc.po_civil_length);
			if (po_length && kmz.proposed_length > po_length) {
				notes.push(__("KMZ route {0} m is more than the PO civil length {1} m: a length extension of about {2} m is needed.", [
					kmz.proposed_length, po_length, Math.round(kmz.proposed_length - po_length),
				]));
			}
			frappe.show_alert({
				message: __("Read KMZ: proposed route {0} m, tapping point {1} m from site.", [
					kmz.proposed_length, kmz.tapping_distance || "?",
				]) + (notes.length ? " " + notes.join(" ") : ""),
				indicator: notes.length ? "orange" : "green",
			}, 12);
		});
	});
}

// Same as ASSIGNMENTS in ug_site.py.
const APPROVALS = [
	{ kind: "Area Manager", prefix: "am", user_field: "am_user" },
	{ kind: "Splicer", prefix: "splicer", user_field: "splicer_user" },
];

function add_approval_buttons(frm) {
	if (frm.is_new()) return;
	// The splicing vendor assigns the splicer (again after a rejection).
	const vendor = frm.doc.vendor_user === frappe.session.user;
	if (frm.doc.splicing_vendor && (vendor || frm.perm[0]?.write)
		&& (!frm.doc.splicer || frm.doc.splicer_approval_status === "Rejected")) {
		frm.add_custom_button(__("Assign Splicer"), () =>
			window.ug_assignment_action(frm.doc.name, "Splicer", "assign", () => frm.reload_doc()), __("Splicer"));
	}
	APPROVALS.forEach(({ kind, prefix, user_field }) => {
		const status = frm.doc[`${prefix}_approval_status`];
		const group = __(kind);
		// Only the assigned person approves, rejects or closes; Admin / Back Office follow the board.
		const assignee = frm.doc[user_field] === frappe.session.user;
		const act = (action) => () => window.ug_assignment_action(frm.doc.name, kind, action, () => frm.reload_doc());
		if (status === "In Progress" && assignee) frm.add_custom_button(__("Close"), act("close"), group);
		if (status !== "Pending") return;
		if (assignee) {
			frm.add_custom_button(__("Approve"), act("approve"), group);
			frm.add_custom_button(__("Reject"), act("reject"), group);
		}
		if (frm.doc[user_field] !== frappe.session.user && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Resend Approval Request"), () =>
				frappe.call({
					method: "underground.underground.doctype.ug_site.ug_site.resend_assignment_request",
					args: { site: frm.doc.name, kind },
				}), group);
		}
	});
}

const KMZ_COLORS = { proposed: "#dc2626", existing: "#2563eb", site: "#16a34a", tapping: "#f59e0b", point: "#6b7280" };

function render_kmz_map(frm) {
	const field = frm.get_field("kmz_map_html");
	if (!field) return;
	if (frm._kmz_map) {
		frm._kmz_observer.disconnect();
		frm._kmz_map.remove();
		frm._kmz_map = null;
	}
	let data = null;
	try {
		data = frm.doc.kmz_map ? JSON.parse(frm.doc.kmz_map) : null;
	} catch (e) {
		data = null;
	}
	if (!data || !window.L) {
		field.$wrapper.html(`<div class="text-muted small">${__("Attach the KMZ file above to see the route on the map.")}</div>`);
		return;
	}

	const swatch = (color, dashed) =>
		`<span style="display:inline-block;width:22px;border-top:4px ${dashed ? "dashed" : "solid"} ${color};vertical-align:middle;margin-right:6px"></span>`;
	const dot = (color) =>
		`<span style="display:inline-block;width:11px;height:11px;border-radius:50%;background:${color};vertical-align:middle;margin-right:6px"></span>`;
	field.$wrapper.html(`
		<div class="ug-kmz-map" style="height:460px;border:1px solid var(--border-color);border-radius:var(--border-radius-md);z-index:1"></div>
		<div class="small text-muted" style="display:flex;flex-wrap:wrap;gap:18px;margin-top:8px">
			<span>${swatch(KMZ_COLORS.proposed)}${__("Proposed route")} <b>${format_number(frm.doc.kmz_route_length || 0, null, 0)} m</b></span>
			<span>${swatch(KMZ_COLORS.existing, true)}${__("Existing route")} <b>${format_number(frm.doc.kmz_existing_route_length || 0, null, 0)} m</b></span>
			<span>${dot(KMZ_COLORS.site)}${__("Site")}</span>
			<span>${dot(KMZ_COLORS.tapping)}${__("Tapping point")}</span>
		</div>`);
	const el = field.$wrapper.find(".ug-kmz-map")[0];

	const map = L.map(el, { scrollWheelZoom: false });
	const tiles = frappe.utils.map_defaults.tiles;
	const street = L.tileLayer(tiles.default_tile.url, tiles.default_tile.options).addTo(map);
	const satellite = L.layerGroup([
		L.tileLayer(tiles.satellite_tile.url, tiles.satellite_tile.options),
		L.tileLayer(tiles.labels_tail.url, tiles.labels_tail.options),
	]);
	L.control.layers({ [__("Street")]: street, [__("Satellite")]: satellite }).addTo(map);
	L.control.scale({ imperial: false }).addTo(map);

	const route = L.geoJSON(data, {
		style: (f) =>
			f.properties.route === "Existing"
				? { color: KMZ_COLORS.existing, weight: 4, dashArray: "8 6" }
				: { color: KMZ_COLORS.proposed, weight: 5 },
		pointToLayer: (f, latlng) =>
			L.circleMarker(latlng, {
				radius: 8,
				color: "#ffffff",
				weight: 2,
				fillOpacity: 1,
				fillColor: { Site: KMZ_COLORS.site, "Tapping Point": KMZ_COLORS.tapping }[f.properties.kind] || KMZ_COLORS.point,
			}),
		onEachFeature: (f, layer) =>
			layer.bindTooltip(frappe.utils.escape_html(f.properties.name || ""), {
				permanent: f.geometry.type === "Point",
				direction: "top",
				offset: [0, -8],
			}),
	}).addTo(map);

	// The map is drawn while its tab may be hidden: fit it once it gets a size.
	let fitted = false;
	frm._kmz_observer = new ResizeObserver(() => {
		if (!el.offsetWidth) return;
		map.invalidateSize();
		if (!fitted && route.getBounds().isValid()) {
			map.fitBounds(route.getBounds(), { padding: [40, 40], maxZoom: 18 });
			fitted = true;
		}
	});
	frm._kmz_observer.observe(el);
	frm._kmz_map = map;
}

function add_punch_points(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Add Punch Points"),
		fields: [
			{ fieldname: "pp_category", label: __("PP Category"), fieldtype: "Link", options: "PP Category", reqd: 1 },
			{
				fieldname: "responsible_party",
				label: __("Responsible Party"),
				fieldtype: "Select",
				options: "\nRKBG\nAirtel",
				description: __("Blank: the category's default."),
			},
			{ fieldname: "cb", fieldtype: "Column Break" },
			{ fieldname: "ff1_status", label: __("Current FF1 Status"), fieldtype: "Data" },
			{ fieldname: "pe_name", label: __("PE Name"), fieldtype: "Data" },
			{ fieldname: "sb", fieldtype: "Section Break" },
			{
				fieldname: "lines",
				label: __("Punch points (one per line)"),
				fieldtype: "Long Text",
				reqd: 1,
				description: __("Paste Airtel's notepad list. Each line becomes one Punch Point."),
			},
		],
		primary_action_label: __("Create"),
		primary_action(values) {
			frappe.call({
				method: "underground.underground.doctype.ug_site.ug_site.add_punch_points",
				args: { site: frm.doc.name, ...values },
				freeze: true,
			}).then((r) => {
				dialog.hide();
				frappe.show_alert({
					message: __("{0} punch point(s) created", [(r.message || []).length]),
					indicator: "green",
				});
				frm.reload_doc();
			});
		},
	});
	dialog.show();
}

// Length laid = difference between the cable's start and end meter readings (saved by the server too).
function set_cable_length(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	frappe.model.set_value(cdt, cdn, "length_m", row.end_reading ? Math.abs(row.end_reading - (row.start_reading || 0)) : 0);
}

frappe.ui.form.on("UG Site Cable", {
	start_reading: set_cable_length,
	end_reading: set_cable_length,
});
