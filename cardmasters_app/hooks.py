app_name = "cardmasters_app"
app_title = "Cardmasters App"
app_publisher = "Shan Torrejos"
app_description = "Contains custom DocTypes and customizations for native DocTypes."
app_email = "storrejos@cardmastersph.com"
app_license = "mit"

# Hydrate specific settings and configurations to JS session boot
boot_session = "cardmasters_app.boot.boot_session"

# Fixtures to export custom fields, workflow structures, and property setters
fixtures = [
    {
        "doctype": "Custom Field",
        "sync_on_migrate": True,
        "filters": [["is_system_generated", "=", 0]]
    },
    {
        "doctype": "Property Setter",
        "sync_on_migrate": True,
        "filters": [["is_system_generated", "=", 0]]
    },
    {
        "doctype": "Workflow State", 
        "sync_on_migrate": True
    },
    {
        "doctype": "Workflow Action Master",
        "sync_on_migrate": True
    }
]

# Client Scripts mapping per DocType
doctype_js = {
    "Customer": "public/js/customer.js",
    "Sales Order": [
        "public/js/sales_order_refactored.js", # SO client validations, edits, and discrepancy warning logic
        "public/js/sales_order/grid_resize.js"  # UI Grid resizing enhancement
    ],
    "Quotation": "public/js/quotation.js",
    "Job Card": [
        "public/js/job_card/remove_assign_job_to_employee.js" # Remove employee assignment restrictions
    ],
    "Artist Card": "public/js/artist_card.js",
    "Work Order": [
        "public/js/work_order.js", # Controlled qty edit form
        "public/js/work_order/skip_material_transfer.js" # Quick action to skip transfers
    ],
    "Petty Cash Request": "public/js/petty_cash_request.js",
    "Stock Entry": "public/js/stock_entry.js",
    "Delivery Note": "public/js/delivery_note.js",
    "Purchase Invoice": "public/js/purchase_invoice.js",
    "Payment Entry": "public/js/payment_entry.js", # Payment reversal out-of-period trigger button
    "Sales Invoice": "public/js/sales_invoice.js",
    "Credit Memo": "public/js/credit_memo.js",
    "Material Request": "public/js/material_request.js"
}

# Override core classes for custom calculations and accounting entry injections
override_doctype_class = {
    "Work Order": "cardmasters_app.cardmasters_app.overrides.work_order.CustomWorkOrder",
    "Stock Entry": "cardmasters_app.cardmasters_app.overrides.stock_entry.CustomStockEntry",
    "Payroll Entry": "cardmasters_app.cardmasters_app.overrides.payroll_entry.CustomPayrollEntry"
}

# Global JS files loaded in Desk
app_include_js = [
    "/assets/cardmasters_app/js/utils.js",
    "/assets/cardmasters_app/js/address_contact_quick_entry_patch.js", # Address patching
    "/assets/cardmasters_app/js/artist_card/multi_artist_filter.js" # Custom list filter for assigned artists
]

# Global CSS files loaded in Desk
app_include_css = [
    "/assets/cardmasters_app/css/sales_order_grid.css"
]

# Server-side document hooks and handlers
doc_events = {
	"Item": {
		"before_insert": "cardmasters_app.cardmasters_app.event_handlers.item.apply_accounting_defaults",
		"after_insert": "cardmasters_app.cardmasters_app.event_handlers.item.create_company_boms"
	},
	"Petty Cash Voucher": {
    	"after_submit": "cardmasters_app.cardmasters_app.event_handlers.petty_cash_voucher.update_pcr_onpcv"
    },
    "Work Order": {
        "after_insert" : [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.pull_sales_order_details", # Inherit SO info
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation" # Tag copy logic
        ],
        "before_submit" : [
            "cardmasters_app.cardmasters_app.services.batch_handler.create_or_assign_work_order_batch", # Create/link SO Item batch on submission
            "cardmasters_app.cardmasters_app.event_handlers.work_order.before_work_order_submit" # Transition SO state to "Begin Production"
        ],
        "on_update_after_submit": [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.work_order_workflow_trigger" # Track completed manufacturing progress
        ],
        "on_cancel": [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.work_order_workflow_trigger" # Revert workflow status if cancelled
        ],
        "validate": [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.validate_so_workflow_state", # Block if parent SO is 'Pending'
            "cardmasters_app.cardmasters_app.services.batch_handler.autofill_work_order_batch_source_fields" # Fill draft batch source fields
        ],
        "onload": [
            "cardmasters_app.cardmasters_app.event_handlers.work_order.warn_data_mismatch" # Alert if SO Item vs WO details mismatch
        ]
    },
    "Stock Entry": {
        "validate": [
            "cardmasters_app.cardmasters_app.event_handlers.stock_entry.before_save_stock_entry" # Set stock consumption accounts
        ],
        "on_submit": [
            "cardmasters_app.cardmasters_app.services.batch_handler.set_batch_received_date_on_population" # Timestamp batch receive date
        ],
        "on_cancel": [
            "cardmasters_app.cardmasters_app.api.return_processing.handle_return_processing_stock_entry_cancel" # Reopen returned item processing status when linked entry is cancelled
        ],
        "before_save": [
            "cardmasters_app.cardmasters_app.services.batch_handler.set_batch_no_for_fg_on_manufacture_entry" # Assign WO batch to FG row
        ]
    },
    "Artist Card": {
        "before_save": [
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.calculate_time_difference" # Time evaluation calculation
        ],
        "before_insert": [
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.update_so_workflow_state",
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.validate_submission", # Force 1 active card rule
            "cardmasters_app.cardmasters_app.event_handlers.artist_card.assign_artist_so" # Map layout artist back to SO
        ],
        "after_insert": [
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation"
        ]
    },
    "Sales Order": {
        "validate": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.set_branch_from_creator_employee",
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.sync_item_branches_with_header",
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.validate_alias_on_facebook_channel",
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.validate_item_rates" # Enforce price list matching
        ],
        "after_submit": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.check_artist_status"
        ],
        "after_insert": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging", # Condition-based auto-tagging
        'on_update_after_submit': [
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.automated_sales_order_tagging",
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.update_work_order_so_status", # Sync workflow state to WO fields
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.validate_item_rates"
        ],
        'before_insert': [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.update_item_class_on_creation_from_quotation"
        ],
        "on_submit": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.manage_grant_usage" # Grant allocation ledger logic
        ],
        "on_cancel": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.manage_grant_usage"
        ],
        "before_save": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.strip_item_specifics_particulars_spaces"
        ],
        "before_update_after_submit": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.strip_item_specifics_particulars_spaces",
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.manage_grant_update_on_submitted_doc" # Sync grant ledger updates retroactively
        ]
    },
    "Sales Order Item": {
        "before_save": [
            "cardmasters_app.cardmasters_app.event_handlers.sales_order.update_item_class_on_update" # Auto-fill default cost center
        ]
    },
    "Job Card": {
        "after_insert" : [
            "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_tags_from_master_on_creation"
        ]
    },
    "Delivery Note": {
        "validate": [
            "cardmasters_app.cardmasters_app.api.return_processing.enforce_return_master_warehouse", # Receive Sales Returns into Cardmasters return warehouse
            "cardmasters_app.cardmasters_app.services.batch_handler.set_batch_no_for_delivery_note" # Automatically query and assign matches
        ],
        "before_submit": [
            "cardmasters_app.cardmasters_app.api.return_processing.enforce_return_master_warehouse" # Server-side enforcement before stock ledger posting
        ]
    },
    "Payment Entry": {
        "on_submit": "cardmasters_app.cardmasters_app.services.outstanding_balance.update_so_balance_on_payment", # Recalculate true outstanding
        "on_cancel": "cardmasters_app.cardmasters_app.services.outstanding_balance.update_so_balance_on_payment"
    },
    "Unreconcile Payment": {
        "on_submit": "cardmasters_app.cardmasters_app.event_handlers.payment_entry.clear_reversal_on_unreconcile_tool" # Clean out-of-period links
    },
    "Journal Entry": {
        "on_submit": "cardmasters_app.cardmasters_app.services.outstanding_balance.update_so_balance_on_payment",
        "on_cancel": [
            "cardmasters_app.cardmasters_app.services.outstanding_balance.update_so_balance_on_payment",
            "cardmasters_app.cardmasters_app.event_handlers.payment_entry.clear_reversal_on_je_cancel"
        ]
    },
    "Tag Link": {
        "after_insert": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_linked_documents_on_master_document_tags_addition" # Sync added tags to WO, Job, Artist Card
    },
    "Raven Message": {
        "after_insert": "cardmasters_app.cardmasters_app.event_handlers.raven.broadcast_raven_update" # Real-time chat sound notification alerts
    },
    "Employee": {
        "autoname": "cardmasters_app.cardmasters_app.overrides.employee.autoname" # Override Employee naming patterns
    },
    "Quotation": {
        "on_update": "cardmasters_app.cardmasters_app.event_handlers.quotation.link_so_to_qtn"
    }
}

# Override whitelisted endpoints to support propagation rules on Tag removals
override_whitelisted_methods = {
    "frappe.desk.doctype.tag.tag.remove_tag": "cardmasters_app.cardmasters_app.event_handlers.tag_automation.sync_linked_documents_on_master_document_tags_removal"
}

# Restrict Artist Cards to only show cards where the artist profile is matching the logged-in user
permission_query_conditions = {
    "Artist Card": "cardmasters_app.cardmasters_app.api.artist_card.artist_filter_listview.get_artist_query"
}

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
