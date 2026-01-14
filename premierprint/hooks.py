app_name = "premierprint"
app_title = "premierprint"
app_publisher = "Munisa"
app_description = "Premier Print"
app_email = "munisabax2002@gmail.com"
app_license = "mit"

fixtures = [
    "Custom Field",
    "Property Setter",
    "Client Script",
    "Server Script",
    "Print Format",
    "Workflow",
    "Workflow State",
    "Workflow Action Master",
    "Role Permission for Page and Report",
    "Custom DocPerm",
    "Currency Exchange",
]
# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "premierprint",
# 		"logo": "/assets/premierprint/logo.png",
# 		"title": "premierprint",
# 		"route": "/premierprint",
# 		"has_permission": "premierprint.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/premierprint/css/premierprint.css"
app_include_js = "/assets/premierprint/js/stock_entry_custom.js"

# include js, css files in header of web template
# web_include_css = "/assets/premierprint/css/premierprint.css"
# web_include_js = "/assets/premierprint/js/premierprint.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "premierprint/public/scss/website"

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
# app_include_icons = "premierprint/public/icons.svg"

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

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "premierprint.utils.jinja_methods",
# 	"filters": "premierprint.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "premierprint.install.before_install"
# after_install = "premierprint.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "premierprint.uninstall.before_uninstall"
# after_uninstall = "premierprint.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "premierprint.utils.before_app_install"
# after_app_install = "premierprint.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "premierprint.utils.before_app_uninstall"
# after_app_uninstall = "premierprint.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "premierprint.notifications.get_notification_config"

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

# DocType Class
# ---------------
# Override standard doctype classes

override_doctype_class = {
	"Item": "premierprint.overrides.item.CustomItem",
	"Customer": "premierprint.overrides.customer.CustomCustomer",
    "Payment Entry": "premierprint.overrides.payment_entry.CustomPaymentEntry"
}

# Document Events
# ---------------
# Hook on document methods and events
# hooks.py

doc_events = {
	"Purchase Invoice": {
		"before_insert": [
			# Auto-fill transport cost from Purchase Order
			"premierprint.services.lcv_service.auto_fill_transport_from_po"
		],
		"validate": [
			# Validate transport data
			"premierprint.services.lcv_service.validate_transport_data"
		],
		"on_submit": [
			# 1. Transport Cost LCV
			"premierprint.services.lcv_service.create_lcv_from_pi",

			# 2. Price Variance LCV
			"premierprint.services.lcv_service.auto_create_lcv_for_price_variance"
		],
		"on_cancel": [
			# Cancel linked Price Variance LCVs
			"premierprint.services.lcv_service.cancel_linked_lcvs"
		]
	}
}
# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------
# Temporarily disabled - utils.py was removed
# scheduler_events = {
#     "hourly": [
#         "premierprint.utils.utils.update_cbu_exchange_rate"
#     ],
# }


# Client Scripts
# IZOH: Fayllar yuklash tartibi muhim! Global fayllar birinchi yuklanadi,
# keyin DocType-specific fayllar yuklanadi.
app_include_js = [
    "/assets/premierprint/js/sales_order.js",
	"/assets/premierprint/js/global_modal_fix.js",
	"/assets/premierprint/js/auto_fetch_account.js",
]

# DocType-specific Client Scripts
doctype_js = {
	"Stock Entry": "stock_entry.js",
	"Purchase Order": "public/js/purchase_order.js",
	"Purchase Invoice": "public/js/purchase_invoice.js",
	"Item": "public/js/item.js",
	"Payment Entry": "public/js/payment_entry.js",
	"Stock Entry": "public/js/stock_entry.js"
}

# scheduler_events = {
# 	"all": [
# 		"premierprint.tasks.all"
# 	],
# 	"daily": [
# 		"premierprint.tasks.daily"
# 	],
# 	"hourly": [
# 		"premierprint.tasks.hourly"
# 	],
# 	"weekly": [
# 		"premierprint.tasks.weekly"
# 	],
# 	"monthly": [
# 		"premierprint.tasks.monthly"
# 	],
# }

# -------

# before_tests = "premierprint.install.before_tests"

# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "premierprint.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "premierprint.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["premierprint.utils.before_request"]
# after_request = ["premierprint.utils.after_request"]

# Job Events
# ----------
# before_job = ["premierprint.utils.before_job"]
# after_job = ["premierprint.utils.after_job"]

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
# 	"premierprint.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

