// Copyright (c) 2026, huda and contributors

const PO_METHOD = "underground.underground.doctype.airtel_po.airtel_po";

frappe.ui.form.on("Airtel PO", {
	setup(frm) {
		frm.set_query("district", () => ({ filters: frm.doc.zone ? { zone: frm.doc.zone } : {} }));
		frm.set_query("replaces_po", () => ({ filters: { name: ["!=", frm.doc.name] } }));
	},

	refresh(frm) {
		if (frm.doc.po_file) {
			frm.add_custom_button(__("Read PO File Again"), () => read_po_file(frm));
		}
		if (!frm.is_new() && (frm.doc.lines || []).length) {
			const label = frm.doc.status === "Applied" ? __("Update Sites") : __("Create / Update Sites");
			frm.add_custom_button(label, () => apply_to_sites(frm)).addClass("btn-primary");
		}
		if (frm.doc.status === "Draft" && !frm.is_new()) {
			frm.dashboard.set_headline(__("Check the lines, then click Create / Update Sites."));
		}
	},

	po_file(frm) {
		if (!frm.doc.po_file) return;
		// The Attach field saves the form right after upload. A new PO skips that save (it would only
		// list empty mandatory fields); a saved one is read after it, or the save overwrites the lines.
		if (frm.is_new()) {
			frm._skip_upload_save = true;
			read_po_file(frm);
		} else frm._read_after_save = true;
	},

	validate(frm) {
		if (frm._skip_upload_save) {
			frm._skip_upload_save = false;
			frappe.validated = false;
		}
	},

	after_save(frm) {
		if (frm._read_after_save) {
			frm._read_after_save = false;
			read_po_file(frm);
		}
	},
});

function read_po_file(frm) {
	frappe.call({
		method: `${PO_METHOD}.read_po_file`,
		args: { file_url: frm.doc.po_file },
		freeze: true,
		freeze_message: __("Reading PO..."),
	}).then(({ message: po }) => {
		if (!po) return;
		if (po.already_exists && po.already_exists !== frm.doc.name) {
			frappe.msgprint({
				title: __("PO already uploaded"),
				indicator: "orange",
				message: __("Airtel PO {0} already exists. Open it instead of uploading again.", [
					`<a href="/app/airtel-po/${encodeURIComponent(po.already_exists)}">${po.already_exists}</a>`,
				]),
			});
		}
		[
			"po_number", "po_no", "po_type", "po_date", "rev_no", "rev_date", "internal_ref",
			"buyer_name", "old_po_ref", "total_value", "payment_terms", "replaces_po", "work_type",
		].forEach((field) => {
			if (po[field] !== undefined) frm.doc[field] = po[field];
		});
		frm.clear_table("lines");
		po.lines.forEach((line) => Object.assign(frm.add_child("lines"), line));
		frm.refresh_fields();
		frm.dirty();

		const matched = po.lines.filter((l) => l.ug_site).length;
		frappe.show_alert({
			message: __("Read {0} line(s) from PO {1} ({2}). {3} matched to existing sites.", [
				po.lines.length, po.po_no, po.po_type, matched,
			]),
			indicator: "green",
		}, 8);
	});
}

function apply_to_sites(frm) {
	const run = () =>
		frappe.call({
			method: `${PO_METHOD}.apply_to_sites`,
			args: { name: frm.doc.name },
			freeze: true,
			freeze_message: __("Updating sites..."),
		}).then(({ message }) => {
			const created = message.created.length;
			frappe.msgprint({
				title: __("Sites updated"),
				indicator: "green",
				message: __("PO lines put on {0} site(s); {1} new site(s) created.", [message.sites.length, created])
					+ "<br>" + message.sites.map((s) => `<a href="/app/ug-site/${s}">${s}</a>`).join(", "),
			});
			frm.reload_doc();
		});
	if (frm.is_dirty()) {
		frm.save().then(run);
	} else {
		run();
	}
}
