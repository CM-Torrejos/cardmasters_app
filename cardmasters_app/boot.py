import frappe

def boot_session(bootinfo):
    # Fetch the cached document and serialize it to a dictionary 
    # so it can be safely passed to the frontend
    settings = frappe.get_cached_doc("Cardmasters Settings")
    bootinfo.cardmasters_settings = settings.as_dict()