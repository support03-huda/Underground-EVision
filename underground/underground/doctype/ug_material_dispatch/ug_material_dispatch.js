// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("UG Material Dispatch", {
	setup(frm) {
		frm.set_query("ug_site", "items", () => ({
			filters: { vlc_code: ["is", "set"], is_mobilization: 0, final_ug_status: "Active" },
		}));
	},
});

// A cable drum's quantity is the difference between its start and end meter readings.
function set_cable_qty(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (row.end_reading) frappe.model.set_value(cdt, cdn, "qty", Math.abs(row.end_reading - (row.start_reading || 0)));
}

frappe.ui.form.on("UG Material Dispatch Item", {
	start_reading: set_cable_qty,
	end_reading: set_cable_qty,
});
