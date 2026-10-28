// Copyright (c) 2026, huda and contributors

const MR_METHOD = "underground.underground.doctype.ug_material_request.ug_material_request";

frappe.ui.form.on("UG Material Request", {
	setup(frm) {
		frm.set_query("ug_site", () => ({
			filters: { is_mobilization: 0, final_ug_status: "Active", am_approval_status: ["in", ["In Progress", "Closed"]] },
		}));
	},

	onload(frm) {
		if (frm.is_new() && frm.doc.ug_site && !(frm.doc.items || []).some((row) => row.item)) fill_items(frm);
	},

	ug_site(frm) {
		if (frm.doc.ug_site) fill_items(frm);
	},

	refresh(frm) {
		const editable = ["Draft", "Rejected"].includes(frm.doc.status);
		// Once sent, the Material Team works from it: the items stay as requested.
		["items", "ug_site", "required_by"].forEach((f) => frm.set_df_property(f, "read_only", !editable && !frm.is_new()));
		if (frm.is_new()) return;
		if (editable && frm.perm[0] && frm.perm[0].write) {
			frm.add_custom_button(__("Send to Material Team"), () =>
				frappe.call({ method: `${MR_METHOD}.send_request`, args: { name: frm.doc.name }, freeze: true })
					.then(() => frm.reload_doc())
			).addClass("btn-primary");
		}
		const material_team = frappe.user.has_role(["UG Material Team", "UG Admin", "System Manager"]);
		if (frm.doc.status === "Requested" && material_team) {
			frm.add_custom_button(__("Material Order"), () => make_order(frm), __("Create"));
			frm.add_custom_button(__("Reject"), () =>
				frappe.prompt(
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason for rejecting"), reqd: 1 },
					({ reason }) => frappe.call({ method: `${MR_METHOD}.reject_request`, args: { name: frm.doc.name, reason } })
						.then(() => frm.reload_doc()),
					__("Reject Material Request"),
					__("Reject")
				));
		}
	},
});

function fill_items(frm) {
	frappe.call({ method: `${MR_METHOD}.get_default_items`, args: { site: frm.doc.ug_site } }).then(({ message }) => {
		if (!(message || []).length) return;
		frm.clear_table("items");
		message.forEach((row) => frm.add_child("items", row));
		frm.refresh_field("items");
	});
}

function make_order(frm) {
	frappe.model.with_doctype("UG Material Order", () => {
		const order = frappe.model.get_new_doc("UG Material Order");
		(frm.doc.items || []).forEach((item) => {
			const row = frappe.model.add_child(order, "items");
			Object.assign(row, {
				ug_site: frm.doc.ug_site,
				node_id: frm.doc.node_id,
				item: item.item,
				cable_type: item.cable_type,
				duct_colour: item.duct_colour,
				ordered_qty: item.qty - (item.ordered_qty || 0),
				uom: item.uom,
				material_request: frm.doc.name,
			});
		});
		frappe.set_route("Form", "UG Material Order", order.name);
	});
}
