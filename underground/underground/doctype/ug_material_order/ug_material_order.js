// Copyright (c) 2026, huda and contributors

frappe.ui.form.on("UG Material Order", {
	setup(frm) {
		frm.set_query("ug_site", "items", () => ({
			filters: { vlc_code: ["is", "set"], is_mobilization: 0, final_ug_status: "Active" },
		}));
		frm.set_query("material_request", "items", (doc, cdt, cdn) => ({
			filters: Object.assign({ status: ["in", ["Requested", "Ordered"]] },
				locals[cdt][cdn].ug_site ? { ug_site: locals[cdt][cdn].ug_site } : {}),
		}));
	},

	refresh(frm) {
		if (!frm.is_new() && frm.doc.status !== "Ordered") {
			frm.add_custom_button(__("Dispatch"), () => {
				frappe.model.with_doctype("UG Material Dispatch", () => {
					const dispatch = frappe.model.get_new_doc("UG Material Dispatch");
					dispatch.material_order = frm.doc.name;
					dispatch.warehouse = frm.doc.warehouse;
					(frm.doc.items || []).forEach((item) => {
						if (!item.received_qty) return;
						const row = frappe.model.add_child(dispatch, "items");
						Object.assign(row, {
							ug_site: item.ug_site,
							node_id: item.node_id,
							item: item.item,
							qty: item.received_qty,
							uom: item.uom,
							cable_id: item.cable_id,
						});
					});
					frappe.set_route("Form", "UG Material Dispatch", dispatch.name);
				});
			}, __("Create"));
		}
	},
});
