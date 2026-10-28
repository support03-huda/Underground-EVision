app_name = "underground"
app_title = "Underground"
app_publisher = "huda"
app_description = "Evision underground module "
app_email = "support03@softworld.co.in"
app_license = "mit"

# UG Fiber ERP: Airtel underground fiber sites from PO receipt to handover.

before_migrate = ["underground.install.create_roles", "underground.install.setup_assignment_board"]
after_install = "underground.install.after_install"
after_migrate = ["underground.install.setup_defaults"]

permission_query_conditions = {
	"UG Site": "underground.permission.ug_site_conditions",
	"ROW Application": "underground.permission.row_application_conditions",
	"UG Daily Progress": "underground.permission.daily_progress_conditions",
	"UG Punch Point": "underground.permission.punch_point_conditions",
	"UG Material Request": "underground.permission.material_request_conditions",
	"UG Splicer": "underground.permission.splicer_conditions",
}
has_permission = {
	"UG Site": "underground.permission.has_site_permission",
	"ROW Application": "underground.permission.has_site_permission",
	"UG Daily Progress": "underground.permission.has_site_permission",
	"UG Punch Point": "underground.permission.has_site_permission",
	"UG Material Request": "underground.permission.has_site_permission",
	"UG Splicer": "underground.permission.has_splicer_permission",
}

scheduler_events = {
	"cron": {
		"30 6 * * *": ["underground.tasks.daily"],
	},
}

# Apps
# ------------------

# required_apps = []

app_logo_url = "/assets/underground/images/underground-logo.svg"
app_home = "/app/ug-dashboard"
app_color = "#1D4E89"

# Each item in the list will be shown as an app in the apps page
add_to_apps_screen = [
	{
		"name": "underground",
		"logo": app_logo_url,
		"title": "Underground",
		"route": app_home,
		"has_permission": "underground.permission.has_app_permission",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/underground/css/underground.css"
app_include_js = "/assets/underground/js/underground.js"

# include js, css files in header of web template
# web_include_css = "/assets/underground/css/underground.css"
# web_include_js = "/assets/underground/js/underground.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "underground/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "underground/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "underground.utils.jinja_methods",
# 	"filters": "underground.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "underground.install.before_install"
# after_install = "underground.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "underground.uninstall.before_uninstall"
# after_uninstall = "underground.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "underground.utils.before_app_install"
# after_app_install = "underground.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "underground.utils.before_app_uninstall"
# after_app_uninstall = "underground.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "underground.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "underground.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["underground.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"underground.tasks.all"
# 	],
# 	"daily": [
# 		"underground.tasks.daily"
# 	],
# 	"hourly": [
# 		"underground.tasks.hourly"
# 	],
# 	"weekly": [
# 		"underground.tasks.weekly"
# 	],
# 	"monthly": [
# 		"underground.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "underground.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "underground.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "underground.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "underground.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["underground.utils.before_request"]
# after_request = ["underground.utils.after_request"]

# Job Events
# ----------
# before_job = ["underground.utils.before_job"]
# after_job = ["underground.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"underground.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []

