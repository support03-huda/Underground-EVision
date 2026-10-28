// Copyright (c) 2026, huda and contributors

frappe.query_reports["Billing Pipeline"] = {
	filters: [
		{ fieldname: "zone", label: __("Zone / Area"), fieldtype: "Link", options: "UG Zone" },
		{ fieldname: "district", label: __("District"), fieldtype: "Link", options: "UG District" },
		{ fieldname: "project_manager", label: __("Project Manager"), fieldtype: "Link", options: "UG Employee" },
		{ fieldname: "work_type", label: __("Work Type"), fieldtype: "Link", options: "UG Work Type" },
		{ fieldname: "billing_status", label: __("Billing Status"), fieldtype: "Select", options: "\nPending\nSubmitted\nApproved\nPaid" },
	],
	onload(report) {
		window.ug_add_report_download(report);
	},
};
