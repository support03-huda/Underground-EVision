// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("UG Daily Progress", {
	setup(frm) {
		frm.set_query("ug_site", () => ({
			filters: { execution_release_date: ["is", "set"], final_ug_status: "Active" },
		}));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.ug_site) frm.trigger("ug_site");
	},

	ug_site(frm) {
		if (!frm.doc.ug_site) return;
		frappe.db.get_value("UG Site", frm.doc.ug_site, ["ibd_included", "work_type"]).then(({ message }) => {
			const show = message && (message.ibd_included || ["IBD", "FTTB"].includes(message.work_type));
			frm.set_value("show_ibd", show ? 1 : 0);
		});
	},
});
