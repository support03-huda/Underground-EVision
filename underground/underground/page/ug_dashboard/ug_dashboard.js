// Copyright (c) 2026, huda and contributors
// UG Dashboard: KPI cards, money, a map of every site coloured by health, stage / ageing / work type
// / weekly progress charts, what needs attention today and an area-wise table. Data: underground.dashboard.

const UGD_COLORS = { blue: "#1d4e89", teal: "#0f9d8a", amber: "#e8a317", red: "#d64545", green: "#2f9e44", violet: "#6d5bd0", slate: "#64748b" };
const UGD_HEALTH = {
	on_track: { color: "#2f9e44", label: __("On track") },
	watch: { color: "#e8a317", label: __("Stage overdue") },
	late: { color: "#d64545", label: __("Past 150 days") },
	done: { color: "#1d4e89", label: __("Completed / closed") },
};

frappe.pages["ug-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("UG Dashboard"), single_column: true });
	wrapper.ug_dashboard = new UGDashboard(page);
};

frappe.pages["ug-dashboard"].on_page_show = function (wrapper) {
	if (wrapper.ug_dashboard && wrapper.ug_dashboard.loaded) wrapper.ug_dashboard.refresh();
};

class UGDashboard {
	constructor(page) {
		this.page = page;
		this.filters = {};
		this.charts = {};
		this.make_filters();
		this.page.set_primary_action(__("Refresh"), () => this.refresh(), "refresh");
		this.page.add_inner_button(__("Assignments"), () => frappe.set_route("underground"));
		this.page.add_inner_button(__("Report Maker"), () => frappe.set_route("ug-report-maker"));
		this.$body = $(`<div class="ugd"><div class="ugd-loading">${__("Loading dashboard...")}</div></div>`).appendTo(this.page.main);
		this.refresh();
	}

	make_filters() {
		[
			["zone", __("Area"), "UG Zone"],
			["work_type", __("Work Type"), "UG Work Type"],
			["project_manager", __("Project Manager"), "UG Employee"],
			["area_manager", __("Area Manager"), "UG Employee"],
		].forEach(([fieldname, label, options]) => {
			this.page.add_field({
				fieldname, label, fieldtype: "Link", options,
				get_query: fieldname === "area_manager" ? () => ({ filters: { designation: "Area Manager" } }) : null,
				change: (e) => {
					const value = this.page.fields_dict[fieldname].get_value();
					if ((this.filters[fieldname] || "") === (value || "")) return;
					this.filters[fieldname] = value;
					this.refresh();
				},
			});
		});
	}

	refresh() {
		return frappe.call({ method: "underground.dashboard.get_data", args: this.filters }).then(({ message }) => {
			this.data = message;
			this.loaded = true;
			this.render();
		});
	}

	// ------------------------------------------------------------ helpers
	esc(v) {
		return frappe.utils.escape_html(v == null ? "" : String(v));
	}

	inr(value) {
		const v = Number(value) || 0;
		const abs = Math.abs(v);
		if (abs >= 1e7) return `₹ ${(v / 1e7).toFixed(2)} Cr`;
		if (abs >= 1e5) return `₹ ${(v / 1e5).toFixed(2)} L`;
		return `₹ ${format_number(v, null, 0)}`;
	}

	pct(part, whole) {
		return whole ? Math.min(100, Math.round((part / whole) * 100)) : 0;
	}

	site_list(filters) {
		frappe.set_route("List", "UG Site", Object.assign({}, this.data.filters, filters));
	}

	// ------------------------------------------------------------ layout
	render() {
		const d = this.data;
		const scope = Object.values(d.filters).filter(Boolean).join(" · ");
		this.$body.html(`
			${this.hero_html(d)}
			<div class="ugd-grid ugd-kpis"></div>
			<div class="ugd-money"></div>
			<div class="ugd-row wide">
				<div class="ugd-panel"><h4>${__("Sites on the map")}<span class="ugd-muted ugd-map-note"></span></h4>
					<div class="ugd-map"></div><div class="ugd-legend"></div></div>
				<div class="ugd-panel"><h4>${__("Needs your action")}</h4><div class="ugd-my"></div>
					<h4 style="margin-top:14px">${__("Work type (active sites)")}</h4><div class="ugd-chart ugd-chart-type"></div></div>
			</div>
			<div class="ugd-row">
				<div class="ugd-panel"><h4>${__("Active sites by stage")}<span class="ugd-muted">${__("red = stage overdue")}</span></h4>
					<div class="ugd-chart ugd-chart-stage"></div></div>
				<div class="ugd-panel"><h4>${__("Site ageing (days since PO)")}<span class="ugd-muted">${__("limit {0} days", [d.limit_day])}</span></h4>
					<div class="ugd-chart ugd-chart-ageing"></div></div>
			</div>
			<div class="ugd-panel"><h4>${__("Weekly progress (km), last 12 weeks")}<span class="ugd-muted">${__("from Daily Progress")}</span></h4>
				<div class="ugd-chart ugd-chart-progress"></div></div>
			<div class="ugd-attn"></div>
			<div class="ugd-panel"><h4>${__("Area-wise")}<span class="ugd-muted">${__("click a row to see its sites")}</span></h4>
				<div class="ugd-table-wrap ugd-areas"></div></div>
			${scope ? `<div class="ugd-muted">${__("Filtered by")}: ${this.esc(scope)}</div>` : ""}
		`);
		this.render_kpis(d.kpis);
		this.render_money(d.money);
		this.render_map(d.map);
		this.render_my_actions(d.attention);
		this.render_charts(d);
		this.render_attention(d.attention);
		this.render_areas(d.areas);
	}

	hero_html(d) {
		const k = d.kpis;
		const done = this.pct(k.td_done_km, k.td_scope_km);
		const name = frappe.boot.user.first_name || frappe.session.user_fullname || "";
		const hour = new Date().getHours();
		const greet = hour < 12 ? __("Good morning") : hour < 17 ? __("Good afternoon") : __("Good evening");
		return `<div class="ugd-hero">
			<h2>${this.esc(greet)}${name ? ", " + this.esc(name) : ""}</h2>
			<div class="ugd-sub">${__("Underground fiber sites: PO to handover in {0} days", [d.limit_day])} · ${frappe.datetime.str_to_user(frappe.datetime.get_today())}</div>
			<div class="ugd-hero-stats">
				<div class="ugd-hero-stat"><div class="v">${k.active}</div><div class="l">${__("Active sites")}</div></div>
				<div class="ugd-hero-stat"><div class="v">${k.completed}</div><div class="l">${__("Completed")}</div></div>
				<div class="ugd-hero-stat"><div class="v">${k.avg_ageing}</div><div class="l">${__("Avg. ageing (days)")}</div></div>
				<div class="ugd-hero-stat"><div class="v">${this.inr(d.money.po_value)}</div><div class="l">${__("PO value")}</div></div>
			</div>
			<div class="ugd-progress">
				<div class="t"><span>${__("T&D done")}: ${format_number(k.td_done_km, null, 2)} / ${format_number(k.td_scope_km, null, 2)} km</span><span>${done}%</span></div>
				<div class="bar"><span style="width:${done}%"></span></div>
			</div>
		</div>`;
	}

	render_kpis(k) {
		const cards = [
			[__("In Execution"), k.in_execution, __("released to the field"), UGD_COLORS.teal, { final_ug_status: "Active", execution_release_date: ["is", "set"] }],
			[__("Stage Overdue"), k.stage_overdue, __("past the stage SLA"), UGD_COLORS.amber, { final_ug_status: "Active", stage_overdue: 1 }],
			[__("Past 150 Days"), k.past_overdue, __("close to the 180-day limit"), UGD_COLORS.red, { final_ug_status: "Active", site_ageing: [">", 150] }],
			[__("Past 180 Days"), k.past_limit, __("over the limit"), "#9b1c1c", { final_ug_status: "Active", site_ageing: [">", 180] }],
			[__("Waiting on ROW"), k.row_pending, __("permission pending / rejected"), UGD_COLORS.violet, { final_ug_status: "Active", row_overall_status: ["in", ["Pending", "Rejected"]] }],
			[__("Open Punch Points"), k.open_pp, __("on active sites"), UGD_COLORS.red, null, () => frappe.set_route("List", "UG Punch Point", { status: ["!=", "Closed"] })],
			[__("Billing Ready"), k.billing_ready, __("not billed yet"), UGD_COLORS.green, { billing_ready: 1, billing_status: "Pending" }],
			[__("All Sites"), k.total, __("in this view"), UGD_COLORS.blue, {}],
		];
		const $grid = this.$body.find(".ugd-kpis");
		cards.forEach(([label, value, sub, color, filters, action]) => {
			$(`<div class="ugd-kpi" style="--accent:${color}">
				<div class="l"><span class="dot"></span>${this.esc(label)}</div>
				<div class="v">${format_number(value || 0, null, 0)}</div>
				<div class="s">${this.esc(sub)}</div></div>`)
				.on("click", () => (action ? action() : this.site_list(filters)))
				.appendTo($grid);
		});
	}

	render_money(m) {
		const cards = [
			[__("PO Value"), m.po_value, __("all sites in view"), UGD_COLORS.blue, null],
			[__("Billed"), m.billed, __("{0}% of PO value", [this.pct(m.billed, m.po_value)]), UGD_COLORS.teal, this.pct(m.billed, m.po_value)],
			[__("Payment Received"), m.paid, __("{0}% of billed", [this.pct(m.paid, m.billed)]), UGD_COLORS.green, this.pct(m.paid, m.billed)],
			[__("Ready, Not Billed"), m.ready_not_billed, __("raise the invoice"), UGD_COLORS.amber, null],
			[__("Retention Pending"), m.retention_pending, __("to recover"), UGD_COLORS.violet, null],
			[__("SD / BG Outstanding"), m.sd_bg_outstanding, __("with authorities"), UGD_COLORS.red, null],
		];
		const $grid = this.$body.find(".ugd-money");
		cards.forEach(([label, value, sub, color, meter]) => {
			$(`<div class="ugd-kpi" style="--accent:${color}">
				<div class="l"><span class="dot"></span>${this.esc(label)}</div>
				<div class="v">${this.inr(value)}</div>
				<div class="s">${this.esc(sub)}</div>
				${meter !== null ? `<div class="ugd-meter"><span style="width:${meter}%"></span></div>` : ""}
			</div>`).on("click", () => frappe.set_route("query-report", "Billing Pipeline")).appendTo($grid);
		});
	}

	// ------------------------------------------------------------ map
	render_map(map) {
		const $map = this.$body.find(".ugd-map");
		const counts = {};
		map.points.forEach((p) => (counts[p.health] = (counts[p.health] || 0) + 1));
		this.$body.find(".ugd-legend").html(Object.entries(UGD_HEALTH).map(([key, h]) =>
			`<span><i style="background:${h.color}"></i>${this.esc(h.label)} <b>${counts[key] || 0}</b></span>`).join(""));
		this.$body.find(".ugd-map-note").text(map.without_location
			? __("{0} site(s) have no location yet (attach the KMZ)", [map.without_location]) : "");
		if (this.map) {
			this.map.remove();
			this.map = null;
		}
		if (!window.L) {
			$map.html(`<div class="ugd-empty">${__("Map is not available in this browser.")}</div>`);
			return;
		}
		const tiles = frappe.utils.map_defaults.tiles;
		const map_obj = L.map($map[0], { scrollWheelZoom: false });
		const street = L.tileLayer(tiles.default_tile.url, tiles.default_tile.options).addTo(map_obj);
		const satellite = L.layerGroup([
			L.tileLayer(tiles.satellite_tile.url, tiles.satellite_tile.options),
			L.tileLayer(tiles.labels_tail.url, tiles.labels_tail.options),
		]);
		L.control.layers({ [__("Street")]: street, [__("Satellite")]: satellite }).addTo(map_obj);
		const markers = map.points.map((p) => {
			const h = UGD_HEALTH[p.health];
			return L.circleMarker([p.lat, p.lon], { radius: 8, color: "#fff", weight: 2, fillColor: h.color, fillOpacity: 0.95 })
				.bindTooltip(this.esc(p.node_id), { direction: "top", offset: [0, -6] })
				.bindPopup(`<b>${this.esc(p.node_id)}</b> ${this.esc(p.node_name || "")}<br>
					${this.esc(p.zone || "")} · ${this.esc(p.work_type || "")}<br>
					${this.esc(p.stage || "")} · <b>${p.ageing}</b> ${__("days")}<br>
					<a href="/app/ug-site/${encodeURIComponent(p.name)}">${__("Open site")} →</a>`)
				.addTo(map_obj);
		});
		if (markers.length) {
			const bounds = L.featureGroup(markers).getBounds();
			map_obj.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
		} else {
			map_obj.setView([19.2, 74.5], 6); // Maharashtra
		}
		this.map = map_obj;
		setTimeout(() => map_obj.invalidateSize(), 200);
	}

	// ------------------------------------------------------------ charts
	chart(selector, options) {
		const el = this.$body.find(selector)[0];
		if (!el || !frappe.Chart) return;
		try {
			this.charts[selector] = new frappe.Chart(el, Object.assign({ height: 250, animate: 1 }, options));
		} catch (e) {
			el.innerHTML = `<div class="ugd-empty">${__("No data yet.")}</div>`;
		}
	}

	render_charts(d) {
		const short = (s) => (s || "").replace(/^\d+ - /, "");
		const stage_has = d.stages.on_time.concat(d.stages.overdue).some(Boolean);
		if (stage_has) {
			this.chart(".ugd-chart-stage", {
				type: "bar",
				data: { labels: d.stages.labels.map(short), datasets: [
					{ name: __("On time"), values: d.stages.on_time },
					{ name: __("Overdue"), values: d.stages.overdue },
				] },
				colors: [UGD_COLORS.blue, UGD_COLORS.red],
				barOptions: { stacked: 1, spaceRatio: 0.4 },
				axisOptions: { xIsSeries: 0 },
			});
		} else {
			this.empty(".ugd-chart-stage");
		}
		if (d.ageing.values.some(Boolean)) {
			this.chart(".ugd-chart-ageing", {
				type: "bar",
				data: { labels: d.ageing.labels, datasets: [{ name: __("Sites"), values: d.ageing.values }] },
				colors: [UGD_COLORS.teal],
				barOptions: { spaceRatio: 0.35 },
			});
		} else {
			this.empty(".ugd-chart-ageing");
		}
		if (d.work_types.values.length) {
			this.chart(".ugd-chart-type", {
				type: "donut",
				height: 220,
				data: { labels: d.work_types.labels, datasets: [{ values: d.work_types.values }] },
				colors: [UGD_COLORS.blue, UGD_COLORS.teal, UGD_COLORS.amber, UGD_COLORS.violet, UGD_COLORS.green, UGD_COLORS.slate],
			});
		} else {
			this.empty(".ugd-chart-type");
		}
		if (d.progress.td.concat(d.progress.blowing).some(Boolean)) {
			this.chart(".ugd-chart-progress", {
				type: "axis-mixed",
				data: { labels: d.progress.labels, datasets: [
					{ name: __("T&D (km)"), values: d.progress.td, chartType: "bar" },
					{ name: __("Cable blowing (km)"), values: d.progress.blowing, chartType: "line" },
				] },
				colors: [UGD_COLORS.teal, UGD_COLORS.violet],
				lineOptions: { dotSize: 5, regionFill: 1 },
				barOptions: { spaceRatio: 0.5 },
			});
		} else {
			this.empty(".ugd-chart-progress", __("No daily progress in the last 12 weeks."));
		}
	}

	empty(selector, text) {
		this.$body.find(selector).html(`<div class="ugd-empty">${this.esc(text || __("No data yet."))}</div>`);
	}

	// ------------------------------------------------------------ lists
	list_html(rows, pill) {
		if (!rows || !rows.length) return `<div class="ugd-empty">${__("Nothing pending.")}</div>`;
		return `<ul class="ugd-list">${rows.map((r, i) => `
			<li data-i="${i}"><div class="main"><div class="n">${this.esc(r.label)}</div><div class="d">${this.esc(r.detail || "")}</div></div>
			${pill(r)}</li>`).join("")}</ul>`;
	}

	bind_list($el, rows, open) {
		$el.find("li").on("click", (e) => open(rows[$(e.currentTarget).data("i")]));
	}

	render_my_actions(a) {
		const rows = a.my_approvals || [];
		const $el = this.$body.find(".ugd-my");
		$el.html(rows.length
			? this.list_html(rows, (r) => `<span class="ugd-pill ${r.status === "Pending" ? "amber" : "blue"}">${this.esc(__(r.status))}</span>`)
			: `<div class="ugd-empty">${__("No approvals waiting for you.")}</div>`);
		this.bind_list($el, rows, (r) => frappe.set_route("Form", "UG Site", r.name));
	}

	render_attention(a) {
		const date = (v) => (v ? frappe.datetime.str_to_user(v) : "");
		const panels = [
			[__("Longest-running sites"), a.late_sites, (r) => `<span class="ugd-pill ${r.days > 150 ? "red" : r.days > 90 ? "amber" : "green"}">${r.days} ${__("days")}</span>`,
				(r) => frappe.set_route("Form", "UG Site", r.name)],
			[__("ROW follow-ups due"), a.row_followups, (r) => `<span class="ugd-pill ${r.overdue ? "red" : "amber"}">${this.esc(date(r.date))}</span>`,
				(r) => frappe.set_route("Form", "ROW Application", r.name),
				a.row_breached ? __("{0} past the SLA", [a.row_breached]) : ""],
			[__("Bank guarantees expiring"), a.bg_expiring, (r) => `<span class="ugd-pill red">${this.esc(date(r.date))}</span>`,
				(r) => frappe.set_route("Form", "ROW Application", r.name)],
			[__("Material requests waiting"), a.material_requests, (r) => `<span class="ugd-pill blue">${this.esc(date(r.date) || __("Requested"))}</span>`,
				(r) => frappe.set_route("Form", "UG Material Request", r.name)],
		];
		const $wrap = this.$body.find(".ugd-attn");
		panels.forEach(([title, rows, pill, open, note]) => {
			const $panel = $(`<div class="ugd-panel"><h4>${this.esc(title)}${note ? `<span class="ugd-muted">${this.esc(note)}</span>` : ""}</h4>${this.list_html(rows, pill)}</div>`)
				.appendTo($wrap);
			this.bind_list($panel, rows || [], open);
		});
	}

	render_areas(areas) {
		if (!areas.length) {
			this.$body.find(".ugd-areas").html(`<div class="ugd-empty">${__("No sites yet.")}</div>`);
			return;
		}
		const max = Math.max(...areas.map((a) => a.active), 1);
		const head = [__("Area"), __("Active"), __("Completed"), __("Avg. Ageing"), __("Overdue"), __("ROW Pending"),
			__("Open PP"), __("Billing Ready"), __("PO Value"), __("Billed")];
		const body = areas.map((a, i) => `<tr data-i="${i}">
			<td><b>${this.esc(a.zone)}</b></td>
			<td><div class="ugd-bar-cell"><span>${a.active}</span><div class="ugd-meter" style="--accent:${UGD_COLORS.blue}"><span style="width:${this.pct(a.active, max)}%"></span></div></div></td>
			<td class="num">${a.completed}</td>
			<td class="num">${a.avg_ageing}</td>
			<td class="num">${a.overdue ? `<span class="ugd-pill red">${a.overdue}</span>` : 0}</td>
			<td class="num">${a.row_pending ? `<span class="ugd-pill amber">${a.row_pending}</span>` : 0}</td>
			<td class="num">${a.open_pp}</td>
			<td class="num">${a.billing_ready ? `<span class="ugd-pill green">${a.billing_ready}</span>` : 0}</td>
			<td class="num">${this.inr(a.po_value)}</td>
			<td class="num">${this.inr(a.billed)}</td>
		</tr>`).join("");
		const $el = this.$body.find(".ugd-areas");
		$el.html(`<table class="ugd-table"><thead><tr>${head.map((h, i) => `<th class="${i ? "num" : ""}">${this.esc(h)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>`);
		$el.find("tr[data-i]").on("click", (e) => {
			const area = areas[$(e.currentTarget).data("i")];
			this.site_list(area.zone && area.zone !== __("Not set") ? { zone: area.zone } : {});
		});
	}
}
