// Copyright (c) 2026, huda and contributors

frappe.query_reports["SLA Breach"] = {
	filters: [
		{ fieldname: "zone", label: __("Zone / Area"), fieldtype: "Link", options: "UG Zone" },
		{ fieldname: "district", label: __("District"), fieldtype: "Link", options: "UG District" },
		{ fieldname: "project_manager", label: __("Project Manager"), fieldtype: "Link", options: "UG Employee" },
		{ fieldname: "work_type", label: __("Work Type"), fieldtype: "Link", options: "UG Work Type" },
		{ fieldname: "current_stage", label: __("Stage"), fieldtype: "Select", options: "\n1 - PO Receipt\n2 - KMZ and Team\n3 - Survey and Feasibility\n4 - SLD and Exceptions\n5 - CWIP, ROW, Job ID, VLC\n6 - Material\n7 - Execution\n8 - FF1, PP, ATC\n9 - Closure and Billing" },
	],
	onload(report) {
		window.ug_add_report_download(report);
	},
};
