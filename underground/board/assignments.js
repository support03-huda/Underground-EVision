// Assignments board (Custom HTML Block "UG Assignments" on the Underground workspace).
// Runs inside the block's shadow root: `root_element` is provided by Frappe.
const TABS = [
	// Only for a splicing vendor: its sites that still need a splicer.
	{ status: "To Assign", label: __("Assign Splicer"), date: "assigned_on", date_label: "", alert: true, vendor: true },
	{ status: "Pending", label: __("Pending Approval"), date: "assigned_on", date_label: __("Assigned On"), alert: true },
	{ status: "In Progress", label: __("In Progress"), date: "approved_on", date_label: __("Approved On") },
	{ status: "Closed", label: __("Closed"), date: "closed_on", date_label: __("Closed On") },
	{ status: "Rejected", label: __("Rejected"), date: "approved_on", date_label: __("Rejected On") },
];
// Admin / Back Office follow only approved work; the assigned person also sees Pending and Rejected.
const OVERSEER_TABS = ["In Progress", "Closed"];
const state = { tab: "Pending", kind: "", rows: [], see_all: false, has_own: false };
const tabs = () => TABS.filter((t) =>
	(state.has_own ? true : OVERSEER_TABS.includes(t.status)) && (!t.vendor || state.rows.some((r) => r.vendor)));
// The vendor sees which of its splicers holds each site.
const show_person = () => state.see_all || state.rows.some((r) => r.vendor);
const $ = (selector) => root_element.querySelector(selector);
const esc = (value) => frappe.utils.escape_html(value == null ? "" : String(value));
const fmt_date = (value) => (value ? frappe.datetime.str_to_user(value) : "");

function load() {
	frappe.call({ method: "underground.underground.doctype.ug_site.ug_site.get_assignments" }).then(({ message }) => {
		state.rows = message.rows || [];
		state.see_all = message.see_all;
		state.has_own = message.has_own;
		// Open on the first tab that has work waiting, so nobody misses a pending approval.
		if (!tabs().some((t) => t.status === state.tab) || !visible(state.tab).length) {
			const first = tabs().find((t) => visible(t.status).length) || tabs()[0];
			state.tab = first.status;
		}
		render();
	});
}

function visible(status) {
	return state.rows.filter((r) => r.status === status && (!state.kind || r.kind === state.kind));
}

function render() {
	$(".ug-tabs").innerHTML = tabs().map((t) => {
		const count = visible(t.status).length;
		const cls = ["ug-tab", t.status === state.tab ? "active" : "", t.alert && count ? "ug-alert" : ""].join(" ");
		return `<button class="${cls}" role="tab" data-tab="${esc(t.status)}">${esc(t.label)}<span class="ug-count">${count}</span></button>`;
	}).join("");

	const tab = TABS.find((t) => t.status === state.tab);
	const rows = visible(state.tab);
	if (!rows.length) {
		$(".ug-body").innerHTML = `<div class="ug-empty">${esc(__("Nothing here."))}</div>`;
		return;
	}
	const show_remarks = ["Closed", "Rejected", "In Progress"].includes(state.tab);
	const head = [
		__("Site"), __("Area"), __("Work Type"), __("Stage"), __("Assigned As"),
		show_person() ? __("Assigned To") : null, tab.date_label,
		show_remarks ? (state.tab === "Rejected" ? __("Reason") : __("Remarks")) : null, "",
	].filter((h) => h !== null);
	$(".ug-body").innerHTML = `
		<table class="ug-table">
			<thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead>
			<tbody>${rows.map((r) => row_html(r, tab, show_remarks)).join("")}</tbody>
		</table>`;
}

function row_html(r, tab, show_remarks) {
	const site = `<div class="ug-site" data-site="${esc(r.site)}">${esc(r.node_id || r.site)}</div>
		<div class="ug-muted">${esc([r.site, r.node_name].filter(Boolean).join(" · "))}</div>`;
	const kind = r.kind === "Splicer" && r.splicing_status
		? `${esc(__(r.kind))}<div class="ug-muted">${esc(__("Splicing"))}: ${esc(__(r.splicing_status))}</div>`
		: esc(__(r.kind));
	const cells = [
		site, esc(r.zone), esc(r.work_type), `<span class="ug-muted">${esc(r.stage)}</span>`, kind,
		show_person() ? esc(r.person) : null, esc(fmt_date(r[tab.date])),
		show_remarks ? `<div class="ug-remarks">${esc(r.remarks)}</div>` : null, actions_html(r),
	].filter((c) => c !== null);
	return `<tr>${cells.map((c) => `<td>${c}</td>`).join("")}</tr>`;
}

function actions_html(r) {
	const button = (action, label, cls, title) =>
		`<button class="btn btn-xs ${cls}" data-action="${action}" data-site="${esc(r.site)}" data-kind="${esc(r.kind)}"`
		+ (title ? ` title="${esc(title)}"` : "") + `>${esc(label)}</button>`;
	// The splicing vendor assigns a splicer, or another one after a rejection.
	if (r.vendor && !r.mine && ["To Assign", "Rejected"].includes(r.status)) {
		const label = r.status === "To Assign" ? __("Assign Splicer") : __("Assign Another");
		return `<div class="ug-actions">${button("assign", label, "btn-primary")}</div>`;
	}
	if (!r.mine) return "";
	if (r.status === "Pending") {
		return `<div class="ug-actions">${button("approve", __("Approve"), "btn-primary")}${button("reject", __("Reject"), "btn-default")}</div>`;
	}
	if (r.status === "In Progress") {
		const title = r.kind === "Splicer" && r.splicing_status !== "Completed"
			? __("Set Splicing Status to Completed on the site first") : "";
		const material = r.kind === "Area Manager" ? button("request_material", __("Request Material"), "btn-default") : "";
		return `<div class="ug-actions">${material}${button("close", __("Close"), "btn-default", title)}</div>`;
	}
	return "";
}

root_element.addEventListener("click", (event) => {
	const tab = event.target.closest("[data-tab]");
	if (tab) {
		state.tab = tab.dataset.tab;
		render();
		return;
	}
	const action = event.target.closest("[data-action]");
	if (action) {
		window.ug_assignment_action(action.dataset.site, action.dataset.kind, action.dataset.action, load);
		return;
	}
	const site = event.target.closest("[data-site]");
	if (site) frappe.set_route("Form", "UG Site", site.dataset.site);
	if (event.target.closest(".ug-refresh")) load();
});
$(".ug-kind").addEventListener("change", (event) => {
	state.kind = event.target.value;
	render();
});
load();
