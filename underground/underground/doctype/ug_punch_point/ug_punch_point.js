// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("UG Punch Point", {
	setup(frm) {
		frm.set_query("sub_category", () => ({
			filters: frm.doc.pp_category ? { pp_category: frm.doc.pp_category } : {},
		}));
	},

	pp_category(frm) {
		if (!frm.doc.pp_category) return;
		frappe.db.get_value("PP Category", frm.doc.pp_category, "default_responsible_party").then(({ message }) => {
			if (message && message.default_responsible_party)
				frm.set_value("responsible_party", message.default_responsible_party);
		});
		frm.set_value("sub_category", null);
	},
});
