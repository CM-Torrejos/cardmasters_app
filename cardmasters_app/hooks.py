app_name = "cardmasters_app"
app_title = "Cardmasters App"
app_publisher = "Shan Torrejos"
app_description = "Contains custom DocTypes and customizations for native DocTypes."
app_email = "storrejos@cardmastersph.com"
app_license = "mit"


fixtures = [
    # Custom Fields 
    {
        "doctype": "Custom Field",
        "sync_on_migrate": True,
        "filters": [
            ["is_system_generated", "=", 0]
        ]
    },

    # Property Setters (overrides to native fields)
    {
        "doctype": "Property Setter",
        "sync_on_migrate": True,
        "filters": [
            ["is_system_generated", "=", 0]
        ]
    },

    # Workflow
    {
        "doctype": "Workflow", 
        "sync_on_migrate": True
    },

    # Workflow states
    {
        "doctype": "Workflow State", 
        "sync_on_migrate": True
    },

    # Workflow action master
    {
        "doctype": "Workflow Action Master",
        "sync_on_migrate": True
    }
]

doctype_js = {
    "Sales Order": "public/js/sales_order.js",
    "Quotation": "public/js/quotation.js",
    "Job Card": "public/js/job_card.js",
    "Petty Cash Count": "public/js/petty_cash_count.js",
    "Artist Card": "public/js/artist_card.js",
    "Work Order": "public/js/work_order.js",
    "Petty Cash Request": "public/js/petty_cash_request.js",
    "Stock Entry": "public/js/stock_entry.js",
    "Purchase Order": "public/js/purchase_order.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Payment Entry": "public/js/payment_entry.js",
    "Material Request": "public/js/material_request.js",
    "Employee": "public/js/employee.js"
}

override_doctype_class = {
    "Job Card": "cardmasters_app.cardmasters_app.api.disable_job_card_validation.JobCard"
}

# load Chart.js legend-filter everywhere
# RIGHT
# app_include_js = "/assets/cardmasters_app/js/chart_legend_filter.js"
# app_include_css = "/assets/cardmasters_app/css/chart_legend_limit.css"
app_include_js = [
    "/assets/cardmasters_app/js/address_contact_quick_entry_patch.js",
    # "/assets/cardmasters_app/js/update_child_items.js"
]

doc_events = {
	"Petty Cash Voucher": {
    	"after_submit": "cardmasters_app.cardmasters_app.event_handlers.petty_cash_voucher.update_pcr_onpcv"
    },
    "Work Order": {

        "after_insert" : [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.inherit_remarks_particulars",
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation"
        ],

        "before_save" : ["cardmasters_app.cardmasters_app.event_handlers.work_order.inherit_remarks_particulars"],

        # "before_insert" : ["cardmasters_app.cardmasters_app.event_handlers.work_order.before_work_order_save"],
        "before_submit" : [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.before_work_order_submit"
        ],
        "after_submit" : ["cardmasters_app.cardmasters_app.event_handlers.work_order.after_submit"]
    },
    "Stock Entry": {
        "after_insert": [
            "cardmasters_app.cardmasters_app.event_handlers.batch_handler.set_batch_no_for_fg_on_manufacture_entry"
        ],
        "validate": [
            "cardmasters_app.cardmasters_app.event_handlers.batch_handler.set_batch_no_for_fg_on_manufacture_entry"
        ]
    },
    "Artist Card": {
        "before_save": [
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.calculate_time_difference"
        ],
        "before_insert": [
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.before_insert",
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.validate_submission",
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.assign_artist_so"
        ],
        "after_insert": [
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation"
        ]
        # "after_save" : [
        #     "cardmasters_app.cardmasters_app.event_handlers.artist_card.assign_artist_so"
        # ]
    },
    "Sales Order": {
        "validate": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.validate_alias_on_facebook_channel",
            # "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging"
            ],
        "after_submit": ["cardmasters_app.cardmasters_app.event_handlers.sales_order.check_artist_status"],
        "after_insert": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging",
        # "on_update": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging",
        'on_update_after_submit': "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging"
    },
    "Job Card": {
        "on_update": ["cardmasters_app.cardmasters_app.event_handlers.job_card.on_job_card_create_handler"],
        "before_save": ["cardmasters_app.cardmasters_app.event_handlers.job_card.before_job_card_save"],
        "before_submit" : ["cardmasters_app.cardmasters_app.event_handlers.job_card.check_all_job_cards_submitted"],
        "after_insert" : [
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation"
        ],
    },
    "Delivery Note": {
        "validate": "cardmasters_app.cardmasters_app.event_handlers.batch_handler.set_batch_no_for_delivery_note"
    },
    "Purchase Order": {
        # "validate": "cardmasters_app.cardmasters_app.event_handlers.purchase_order.validate_po_revolving"
    },
    "Material Request": {
        "validate": ["cardmasters_app.cardmasters_app.event_handlers.material_request.validate_material_request"]
    },
    "Payment Entry": {
        "on_submit": "cardmasters_app.cardmasters_app.api.outstanding_balance.update_so_balance_on_payment",
        "on_cancel": "cardmasters_app.cardmasters_app.api.outstanding_balance.update_so_balance_on_payment"
    },
    "Journal Entry": {
        "on_submit": "cardmasters_app.cardmasters_app.api.outstanding_balance.update_so_balance_on_payment",
        "on_cancel": "cardmasters_app.cardmasters_app.api.outstanding_balance.update_so_balance_on_payment"
    },
    "Tag Link": {
        "after_insert": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_linked_documents_on_master_document_tags_addition"
    }
}

override_whitelisted_methods = {
    "frappe.desk.doctype.tag.tag.remove_tag": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_linked_documents_on_master_documemt_tags_removal"
}

app_include_css = "/assets/cardmasters_app/css/cardmasters_app.css"
app_include_js = "/assets/cardmasters_app/js/theme_switcher.js"

# Apps
# ------------------

required_apps = ["frappe/hrms"]

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "cardmasters_app",
# 		"logo": "/assets/cardmasters_app/logo.png",
# 		"title": "Cardmasters App",
# 		"route": "/cardmasters_app",
# 		"has_permission": "cardmasters_app.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/cardmasters_app/css/cardmasters_app.css"
# app_include_js = "/assets/cardmasters_app/js/cardmasters_app.js"

# include js, css files in header of web template
# web_include_css = "/assets/cardmasters_app/css/cardmasters_app.css"
# web_include_js = "/assets/cardmasters_app/js/cardmasters_app.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "cardmasters_app/public/scss/website"

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
# app_include_icons = "cardmasters_app/public/icons.svg"

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
# 	"methods": "cardmasters_app.utils.jinja_methods",
# 	"filters": "cardmasters_app.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "cardmasters_app.install.before_install"
# after_install = "cardmasters_app.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "cardmasters_app.uninstall.before_uninstall"
# after_uninstall = "cardmasters_app.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "cardmasters_app.utils.before_app_install"
# after_app_install = "cardmasters_app.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "cardmasters_app.utils.before_app_uninstall"
# after_app_uninstall = "cardmasters_app.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "cardmasters_app.notifications.get_notification_config"

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

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
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
# 		"cardmasters_app.tasks.all"
# 	],
# 	"daily": [
# 		"cardmasters_app.tasks.daily"
# 	],
# 	"hourly": [
# 		"cardmasters_app.tasks.hourly"
# 	],
# 	"weekly": [
# 		"cardmasters_app.tasks.weekly"
# 	],
# 	"monthly": [
# 		"cardmasters_app.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "cardmasters_app.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "cardmasters_app.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "cardmasters_app.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["cardmasters_app.utils.before_request"]
# after_request = ["cardmasters_app.utils.after_request"]

# Job Events
# ----------
# before_job = ["cardmasters_app.utils.before_job"]
# after_job = ["cardmasters_app.utils.after_job"]

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
# 	"cardmasters_app.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

