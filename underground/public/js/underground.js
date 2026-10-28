// Copyright (c) 2026, huda and contributors
// Loaded on every desk page (hooks.app_include_js).

// Approve / Reject (with reason) / Close an Area Manager or Splicer assignment. Used by the UG Site
// form and by the Assignments board on the Underground workspace.
window.ug_assignment_action = function (site, kind, action, done) {
	const METHOD = "underground.underground.doctype.ug_site.ug_site";
	const call = (method, args) =>
		frappe.call({ method: `${METHOD}.${method}`, args: { site, kind, ...args }, freeze: true })
			.then(({ message: status }) => {
				frappe.show_alert({
					message: __("{0} on {1}: {2}", [__(kind), site, __(status)]),
					indicator: status === "Rejected" ? "red" : "green",
				});
				done && done(status);
			});
	if (action === "approve") {
		frappe.confirm(__("Approve site {0} as {1}? It moves to In Progress.", [site, __(kind)]), () =>
			call("respond_assignment", { approve: 1 }).then(() => {
				// After approving, the Area Manager asks for the site's material.
				if (kind === "Area Manager") {
					frappe.confirm(__("Request material for site {0} now?", [site]), () =>
						frappe.new_doc("UG Material Request", { ug_site: site }));
				}
			}));
	} else if (action === "request_material") {
		frappe.new_doc("UG Material Request", { ug_site: site });
	} else if (action === "assign") {
		// The splicing vendor picks one of its own splicers.
		frappe.db.get_value("UG Site", site, "splicing_vendor").then(({ message }) => {
			const vendor = message && message.splicing_vendor;
			frappe.prompt(
				{
					fieldname: "splicer", fieldtype: "Link", options: "UG Splicer", label: __("Splicer"), reqd: 1,
					get_query: () => ({ filters: { vendor, is_active: 1 } }),
					description: __("Splicers of {0}. Add a new one in UG Splicer.", [vendor]),
				},
				({ splicer }) => frappe.call({ method: `${METHOD}.assign_splicer`, args: { site, splicer }, freeze: true })
					.then(() => {
						frappe.show_alert({ message: __("{0} assigned to {1}; approval request sent.", [splicer, site]), indicator: "green" });
						done && done("Pending");
					}),
				__("Assign Splicer to {0}", [site]),
				__("Assign")
			);
		});
	} else if (action === "reject") {
		frappe.prompt(
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Reason for rejecting"), reqd: 1 },
			({ remarks }) => call("respond_assignment", { approve: 0, remarks }),
			__("Reject site {0} as {1}", [site, __(kind)]),
			__("Reject")
		);
	} else if (action === "close") {
		frappe.prompt(
			{ fieldname: "remarks", fieldtype: "Small Text", label: __("Closing remarks (optional)") },
			({ remarks }) => call("close_assignment", { remarks }),
			__("Close site {0} as {1}", [site, __(kind)]),
			__("Close")
		);
	}
};

// Download a Report Maker file (xlsx, pdf, doc, csv) without leaving the page; errors show as a message.
window.ug_download = function (args, fmt) {
	frappe.show_alert({ message: __("Preparing the file..."), indicator: "blue" }, 3);
	const body = new URLSearchParams();
	Object.entries({ ...args, fmt }).forEach(([key, value]) => {
		if (value !== undefined && value !== null) body.append(key, typeof value === "string" ? value : JSON.stringify(value));
	});
	return fetch("/api/method/underground.report_maker.download", {
		method: "POST",
		headers: { "X-Frappe-CSRF-Token": frappe.csrf_token, Accept: "application/json" },
		body,
	}).then(async (response) => {
		if (!response.ok) {
			let message = __("The file could not be made.");
			try {
				const data = await response.json();
				message = data._server_messages
					? JSON.parse(data._server_messages).map((m) => JSON.parse(m).message).join("<br>")
					: data.exception || message;
			} catch (e) {
				// not JSON: keep the plain message
			}
			frappe.msgprint({ title: __("Download failed"), message, indicator: "red" });
			return;
		}
		const blob = await response.blob();
		const match = (response.headers.get("Content-Disposition") || "").match(/filename\*?=(?:UTF-8'')?"?([^";]+)"?/i);
		const link = document.createElement("a");
		link.href = URL.createObjectURL(blob);
		link.download = match ? decodeURIComponent(match[1]) : `report.${fmt}`;
		document.body.appendChild(link);
		link.click();
		link.remove();
		setTimeout(() => URL.revokeObjectURL(link.href), 2000);
	});
};

// Download buttons on every Underground report: frappe.query_reports[name].onload calls this.
window.ug_add_report_download = function (report) {
	const source = `report:${report.report_name}`;
	[["xlsx", __("Excel")], ["pdf", __("PDF")], ["doc", __("Word")], ["csv", __("CSV")]].forEach(([fmt, label]) =>
		report.page.add_inner_button(label, () =>
			window.ug_download({
				source,
				filters: report.get_filter_values(),
				total_row: report.report_doc && report.report_doc.add_total_row ? 1 : 0,
			}, fmt), __("Download")));
	report.page.add_inner_button(__("Open in Report Maker"), () => {
		frappe.route_options = { source, filters: report.get_filter_values() };
		frappe.set_route("ug-report-maker");
	});
};
