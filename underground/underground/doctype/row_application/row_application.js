// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("ROW Application", {
	setup(frm) {
		frm.set_query("ug_site", () => ({ filters: { is_mobilization: 0, final_ug_status: "Active" } }));
	},

	refresh(frm) {
		if (frm.doc.sla_breached) frm.dashboard.add_indicator(__("ROW SLA breached"), "red");
		if (["Expiring", "Expired"].includes(frm.doc.bg_status))
			frm.dashboard.add_indicator(__("BG {0}", [frm.doc.bg_status]), "orange");
	},

	permission_status(frm) {
		if (frm.doc.permission_status === "Received" && !frm.doc.permission_date)
			frm.set_value("permission_date", frappe.datetime.get_today());
		if (frm.doc.permission_status === "Reapplied" && !frm.doc.reapplied_date)
			frm.set_value("reapplied_date", frappe.datetime.get_today());
	},

	application_status(frm) {
		if (frm.doc.application_status !== "Draft" && !frm.doc.application_date)
			frm.set_value("application_date", frappe.datetime.get_today());
	},
});
