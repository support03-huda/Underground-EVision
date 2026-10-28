// Copyright (c) 2026, huda and contributors

frappe.query_reports["ATC Tracker"] = {
	filters: [
		{ fieldname: "zone", label: __("Zone / Area"), fieldtype: "Link", options: "UG Zone" },
		{ fieldname: "district", label: __("District"), fieldtype: "Link", options: "UG District" },
		{ fieldname: "project_manager", label: __("Project Manager"), fieldtype: "Link", options: "UG Employee" },
		{ fieldname: "work_type", label: __("Work Type"), fieldtype: "Link", options: "UG Work Type" },
		{ fieldname: "ug_site", label: __("UG Site"), fieldtype: "Link", options: "UG Site" },
		{ fieldname: "status", label: __("Status"), fieldtype: "Select", options: "\nOpen\nIn Progress\nClosed\nNot Closed", default: "Not Closed" },
		{ fieldname: "responsible_party", label: __("Responsible Party"), fieldtype: "Select", options: "\nRKBG\nAirtel" },
		{ fieldname: "pp_category", label: __("PP Category"), fieldtype: "Link", options: "PP Category" },
	],
	onload(report) {
		window.ug_add_report_download(report);
	},
};
