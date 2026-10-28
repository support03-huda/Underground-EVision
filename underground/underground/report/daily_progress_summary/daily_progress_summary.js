// Copyright (c) 2026, huda and contributors

frappe.query_reports["Daily Progress Summary"] = {
	filters: [
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", default: frappe.datetime.month_start(), reqd: 1 },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", default: frappe.datetime.get_today(), reqd: 1 },
		{ fieldname: "zone", label: __("Zone / Area"), fieldtype: "Link", options: "UG Zone" },
		{ fieldname: "district", label: __("District"), fieldtype: "Link", options: "UG District" },
		{ fieldname: "project_manager", label: __("Project Manager"), fieldtype: "Link", options: "UG Employee" },
		{ fieldname: "work_type", label: __("Work Type"), fieldtype: "Link", options: "UG Work Type" },
		{ fieldname: "ug_site", label: __("UG Site"), fieldtype: "Link", options: "UG Site" },
		{ fieldname: "vendor", label: __("Vendor / Team"), fieldtype: "Link", options: "UG Vendor" },
	],
	onload(report) {
		window.ug_add_report_download(report);
	},
};
