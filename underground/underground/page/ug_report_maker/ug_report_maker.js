// Copyright (c) 2026, huda and contributors
// Report Maker: pick any Underground list or ready report, its columns, filters, sorting, grouping
// and totals; preview it and download it as Excel, PDF, Word or CSV. Saved reports keep the choices.

const RM_METHOD = "underground.report_maker";
const RM_FORMATS = [["xlsx", "Excel (.xlsx)"], ["pdf", "PDF"], ["doc", "Word (.doc)"], ["csv", "CSV"]];

frappe.pages["ug-report-maker"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Report Maker"), single_column: true });
	wrapper.report_maker = new UGReportMaker(page);
};

frappe.pages["ug-report-maker"].on_page_show = function (wrapper) {
	// "Open in Report Maker" from a report passes its source and filters.
	const options = frappe.route_options;
	if (options && options.source && wrapper.report_maker) {
		frappe.route_options = null;
		wrapper.report_maker.ready.then(() =>
			wrapper.report_maker.apply({ source: options.source, filters: options.filters || {} }));
	}
};

class UGReportMaker {
	constructor(page) {
		this.page = page;
		this.reset_state();
		this.make();
		this.ready = Promise.all([this.load_sources(), this.load_templates()]);
	}

	reset_state() {
		this.fields = [];
		this.selected = [];
		this.filter_group = null;
		this.report_controls = {};
	}

	// ------------------------------------------------------------ layout
	make() {
		const esc = frappe.utils.escape_html;
		this.$body = $(`
			<div class="ugrm">
				<div class="ugrm-card">
					<div class="ugrm-row">
						<label class="ugrm-field"><span>${esc(__("1. Data from"))}</span>
							<select class="form-control ugrm-source"></select></label>
						<label class="ugrm-field"><span>${esc(__("Report title"))}</span>
							<input class="form-control ugrm-title" placeholder="${esc(__("Optional: printed on the file"))}"></label>
						<label class="ugrm-field"><span>${esc(__("Saved reports"))}</span>
							<select class="form-control ugrm-templates"></select></label>
					</div>
				</div>
				<div class="ugrm-card">
					<div class="ugrm-head">
						<b>${esc(__("2. Columns"))}</b>
						<span class="ugrm-muted ugrm-col-count"></span>
						<input class="form-control input-xs ugrm-col-search" placeholder="${esc(__("Search columns"))}">
						<a class="ugrm-link" data-cols="default">${esc(__("Default"))}</a>
						<a class="ugrm-link" data-cols="all">${esc(__("All"))}</a>
						<a class="ugrm-link" data-cols="none">${esc(__("Clear"))}</a>
					</div>
					<div class="ugrm-columns"><div class="ugrm-muted">${esc(__("Pick where the data comes from first."))}</div></div>
				</div>
				<div class="ugrm-card">
					<div class="ugrm-head"><b>${esc(__("3. Filters"))}</b></div>
					<div class="ugrm-filters"></div>
				</div>
				<div class="ugrm-card">
					<div class="ugrm-head"><b>${esc(__("4. Sort, group and total"))}</b></div>
					<div class="ugrm-row">
						<label class="ugrm-field"><span>${esc(__("Sort by"))}</span><select class="form-control ugrm-order"></select></label>
						<label class="ugrm-field"><span>${esc(__("Order"))}</span>
							<select class="form-control ugrm-sort">
								<option value="asc">${esc(__("Ascending (A→Z, old→new, small→big)"))}</option>
								<option value="desc">${esc(__("Descending (Z→A, new→old, big→small)"))}</option>
							</select></label>
						<label class="ugrm-field"><span>${esc(__("Group by: one row per value, with count and totals"))}</span>
							<select class="form-control ugrm-group"></select></label>
						<label class="ugrm-check"><input type="checkbox" class="ugrm-total"> ${esc(__("Add total row"))}</label>
					</div>
				</div>
				<div class="ugrm-card">
					<div class="ugrm-head"><b>${esc(__("5. Preview"))}</b> <span class="ugrm-muted ugrm-count"></span></div>
					<div class="ugrm-preview"><div class="ugrm-muted">${esc(__("Press Preview to see the rows; Download gives the full file."))}</div></div>
				</div>
			</div>`).appendTo(this.page.main);

		this.page.set_primary_action(__("Preview"), () => this.preview(), "view");
		RM_FORMATS.forEach(([fmt, label]) => this.page.add_inner_button(__(label), () => this.download(fmt), __("Download")));
		this.page.add_inner_button(__("Save Report"), () => this.save_template());
		this.page.add_menu_item(__("Delete Saved Report"), () => this.delete_template());
		this.page.add_menu_item(__("New Report"), () => this.apply({ source: "" }));

		this.$("source").on("change", (e) => this.set_source(e.target.value));
		this.$("templates").on("change", (e) => this.pick_template(e.target.value));
		this.$("col-search").on("input", () => this.render_columns());
		this.$body.on("click", "[data-cols]", (e) => this.pick_columns(e.currentTarget.dataset.cols));
		this.$body.on("change", ".ugrm-columns input", (e) => {
			const field = e.target.value;
			this.selected = e.target.checked ? [...this.selected, field] : this.selected.filter((f) => f !== field);
			this.render_columns();
		});
	}

	$(name) {
		return this.$body.find(`.ugrm-${name}`);
	}

	// ------------------------------------------------------------ sources and saved reports
	load_sources() {
		return frappe.call({ method: `${RM_METHOD}.get_sources` }).then(({ message }) => {
			const opt = (o) => `<option value="${frappe.utils.escape_html(o.value)}">${frappe.utils.escape_html(o.label)}</option>`;
			this.$("source").html(
				`<option value="">${frappe.utils.escape_html(__("Select..."))}</option>`
				+ `<optgroup label="${frappe.utils.escape_html(__("Lists (pick any columns)"))}">${message.lists.map(opt).join("")}</optgroup>`
				+ `<optgroup label="${frappe.utils.escape_html(__("Ready reports"))}">${message.reports.map(opt).join("")}</optgroup>`
			);
		});
	}

	load_templates(select) {
		return frappe.call({ method: `${RM_METHOD}.get_templates` }).then(({ message }) => {
			this.templates = message || [];
			const mine = this.templates.filter((t) => t.owner === frappe.session.user);
			const shared = this.templates.filter((t) => t.owner !== frappe.session.user);
			const opt = (t) => `<option value="${t.name}">${frappe.utils.escape_html(t.template_name)}${t.is_public && t.owner === frappe.session.user ? " ✓" : ""}</option>`;
			this.$("templates").html(
				`<option value="">${frappe.utils.escape_html(this.templates.length ? __("Open a saved report...") : __("None saved yet"))}</option>`
				+ (mine.length ? `<optgroup label="${__("Mine")}">${mine.map(opt).join("")}</optgroup>` : "")
				+ (shared.length ? `<optgroup label="${__("Shared by others")}">${shared.map(opt).join("")}</optgroup>` : "")
			);
			if (select) this.$("templates").val(select);
		});
	}

	is_report() {
		return (this.source || "").startsWith("report:");
	}

	set_source(source, keep_template) {
		this.source = source;
		this.reset_state();
		if (!keep_template) {
			this.template = null;
			this.$("templates").val("");
		}
		this.$("source").val(source);
		this.$("filters").empty();
		this.$("preview").html("");
		this.$("count").text("");
		if (!source) {
			this.render_columns();
			return Promise.resolve();
		}
		const columns = this.is_report()
			? Promise.resolve()
			: frappe.call({ method: `${RM_METHOD}.get_fields`, args: { source } }).then(({ message }) => {
				this.fields = message || [];
				this.selected = this.fields.filter((f) => f.default).map((f) => f.fieldname);
			});
		const filters = this.is_report() ? this.make_report_filters() : this.make_list_filters();
		return Promise.all([columns, filters]).then(() => this.render_columns());
	}

	pick_template(name) {
		const template = (this.templates || []).find((t) => t.name === name);
		if (!template) return;
		this.apply({ ...JSON.parse(template.config || "{}"), source: template.source }, template);
	}

	// Load a whole set of choices (a saved report, or a report opened from its page).
	apply(config, template) {
		return this.set_source(config.source || "", Boolean(template)).then(() => {
			this.template = template || null;
			this.$("title").val(config.title || (template ? template.template_name : ""));
			if (config.columns && config.columns.length) this.selected = [...config.columns];
			this.set_filters(config.filters);
			this.render_columns();
			this.$("order").val(config.order_by || "");
			this.$("sort").val(config.sort_order || "asc");
			this.$("group").val(config.group_by || "");
			this.$("total").prop("checked", Boolean(config.total_row));
			if (config.source) this.preview();
		});
	}

	// ------------------------------------------------------------ columns
	pick_columns(which) {
		if (which === "none") this.selected = [];
		else if (which === "all") this.selected = this.fields.map((f) => f.fieldname);
		else this.selected = this.fields.filter((f) => f.default).map((f) => f.fieldname);
		this.render_columns();
	}

	render_columns() {
		const esc = frappe.utils.escape_html;
		const search = (this.$("col-search").val() || "").toLowerCase();
		if (!this.fields.length) {
			this.$("columns").html(`<div class="ugrm-muted">${esc(this.is_report()
				? __("A ready report has its own columns: press Preview to list them, then untick what you do not need.")
				: __("Pick where the data comes from first."))}</div>`);
		} else {
			this.$("columns").html(this.fields
				.filter((f) => !search || (f.label || "").toLowerCase().includes(search))
				.map((f) => {
					const position = this.selected.indexOf(f.fieldname);
					return `<label title="${esc(f.fieldname)}"><input type="checkbox" value="${esc(f.fieldname)}" ${position >= 0 ? "checked" : ""}>
						<span>${esc(f.label)}</span>${position >= 0 ? `<span class="ugrm-order-no">${position + 1}</span>` : ""}</label>`;
				}).join("") || `<div class="ugrm-muted">${esc(__("No column matches."))}</div>`);
		}
		this.$("col-count").text(this.fields.length
			? __("{0} of {1} ticked; they print in the order you tick them", [this.selected.length, this.fields.length]) : "");
		this.render_sort_options();
	}

	render_sort_options() {
		const esc = frappe.utils.escape_html;
		const chosen = this.selected.length ? this.selected : this.fields.map((f) => f.fieldname);
		const options = chosen.map((name) => this.fields.find((f) => f.fieldname === name)).filter(Boolean)
			.map((f) => `<option value="${esc(f.fieldname)}">${esc(f.label)}</option>`).join("");
		["order", "group"].forEach((name) => {
			const $select = this.$(name);
			const value = $select.val();
			$select.html(`<option value="">${esc(name === "order" ? __("Default") : __("No grouping"))}</option>${options}`);
			if (value && chosen.includes(value)) $select.val(value);
		});
	}

	// ------------------------------------------------------------ filters
	make_list_filters() {
		const $area = $(`<div></div>`).appendTo(this.$("filters"));
		return new Promise((resolve) => {
			frappe.model.with_doctype(this.source, () => {
				this.filter_group = new frappe.ui.FilterGroup({ parent: $area, doctype: this.source, on_change: () => {} });
				resolve();
			});
		});
	}

	make_report_filters() {
		const name = this.source.slice("report:".length);
		return frappe.call({ method: "frappe.desk.query_report.get_script", args: { report_name: name } }).then(({ message }) => {
			frappe.query_reports = frappe.query_reports || {};
			if (!frappe.query_reports[name] && message && message.script) frappe.dom.eval(message.script);
			const definition = frappe.query_reports[name] || { filters: [] };
			const $grid = $(`<div class="ugrm-filter-fields"></div>`).appendTo(this.$("filters"));
			(definition.filters || []).forEach((df) => {
				const control = frappe.ui.form.make_control({
					df: { ...df, reqd: 0, onchange: null },
					parent: $("<div></div>").appendTo($grid),
					render_input: true,
				});
				if (df.default !== undefined) control.set_value(typeof df.default === "function" ? df.default() : df.default);
				this.report_controls[df.fieldname] = control;
			});
			if (!(definition.filters || []).length) $grid.html(`<div class="ugrm-muted">${__("This report has no filters.")}</div>`);
		});
	}

	get_filters() {
		if (this.is_report()) {
			const values = {};
			Object.entries(this.report_controls).forEach(([fieldname, control]) => {
				const value = control.get_value();
				if (value !== undefined && value !== null && value !== "") values[fieldname] = value;
			});
			return values;
		}
		return this.filter_group ? this.filter_group.get_filters() : [];
	}

	set_filters(filters) {
		if (!filters) return;
		if (this.is_report()) {
			Object.entries(filters).forEach(([fieldname, value]) => {
				if (this.report_controls[fieldname]) this.report_controls[fieldname].set_value(value);
			});
		} else if (this.filter_group && filters.length) {
			this.filter_group.add_filters_to_filter_group(filters);
		}
	}

	// ------------------------------------------------------------ preview, download, save
	args() {
		return {
			source: this.source,
			columns: this.selected,
			filters: this.get_filters(),
			order_by: this.$("order").val() || null,
			sort_order: this.$("sort").val(),
			group_by: this.$("group").val() || null,
			total_row: this.$("total").is(":checked") ? 1 : 0,
			title: this.$("title").val() || null,
		};
	}

	check_source() {
		if (this.source) return true;
		frappe.msgprint(__("Pick where the data comes from (step 1)."));
		return false;
	}

	preview() {
		if (!this.check_source()) return;
		const esc = frappe.utils.escape_html;
		frappe.call({ method: `${RM_METHOD}.preview`, args: this.args(), freeze: true, freeze_message: __("Fetching rows...") })
			.then(({ message }) => {
				const { columns, rows, total, numeric, available } = message;
				// A ready report lists its columns only once it has run.
				if (this.is_report() && available) {
					this.fields = available.map((c) => ({ fieldname: c.fieldname, label: c.label, default: 1 }));
					if (!this.selected.length) this.selected = this.fields.map((f) => f.fieldname);
					this.render_columns();
				}
				const has_total = this.$("total").is(":checked") && rows.length;
				this.$("count").text(total > rows.length
					? __("Showing the first {0} of {1} rows. Download gives all of them.", [rows.length, total])
					: __("{0} rows", [total - (has_total ? 1 : 0)]));
				if (!rows.length) {
					this.$("preview").html(`<div class="ugrm-muted">${esc(__("No rows match the filters."))}</div>`);
					return;
				}
				const head = columns.map((c, i) => `<th class="${numeric[i] ? "num" : ""}">${esc(c.label)}</th>`).join("");
				const body = rows.map((row, r) => {
					const total_cls = has_total && r === rows.length - 1 && total === rows.length ? "ugrm-total" : "";
					return `<tr class="${total_cls}">${row.map((v, i) => `<td class="${numeric[i] ? "num" : ""}">${esc(v)}</td>`).join("")}</tr>`;
				}).join("");
				this.$("preview").html(`<table class="ugrm-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`);
			});
	}

	download(fmt) {
		if (!this.check_source()) return;
		window.ug_download(this.args(), fmt);
	}

	save_template() {
		if (!this.check_source()) return;
		const current = this.template;
		const dialog = new frappe.ui.Dialog({
			title: __("Save Report"),
			fields: [
				{ fieldname: "template_name", fieldtype: "Data", label: __("Report Name"), reqd: 1,
				  default: current ? current.template_name : this.$("title").val() },
				{ fieldname: "is_public", fieldtype: "Check", label: __("Everyone can use it"),
				  default: current ? current.is_public : 0 },
				{ fieldname: "as_new", fieldtype: "Check", label: __("Save as a new report"), default: 0,
				  hidden: !(current && current.owner === frappe.session.user) },
			],
			primary_action_label: __("Save"),
			primary_action: (values) => {
				const config = this.args();
				delete config.source;
				const overwrite = current && current.owner === frappe.session.user && !values.as_new;
				frappe.call({
					method: `${RM_METHOD}.save_template`,
					args: { template_name: values.template_name, source: this.source, config: JSON.stringify(config),
					        is_public: values.is_public, name: overwrite ? current.name : null },
				}).then(({ message }) => {
					dialog.hide();
					frappe.show_alert({ message: __("Saved: {0}", [values.template_name]), indicator: "green" });
					this.load_templates(message).then(() => {
						this.template = this.templates.find((t) => t.name === message) || null;
					});
				});
			},
		});
		dialog.show();
	}

	delete_template() {
		const template = this.template;
		if (!template || template.owner !== frappe.session.user) {
			frappe.msgprint(__("Open one of your saved reports first."));
			return;
		}
		frappe.confirm(__("Delete saved report {0}?", [template.template_name]), () =>
			frappe.call({ method: `${RM_METHOD}.delete_template`, args: { name: template.name } }).then(() => {
				this.template = null;
				this.load_templates();
			}));
	}
}
