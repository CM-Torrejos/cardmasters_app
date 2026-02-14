import frappe

def get_artist_query(user, doctype=None):
    # Read the session variable we set in the JS callback
    artist = frappe.cache().get_value(f"search_artist_{user}")
    
    if artist:
        safe_val = frappe.db.escape(artist)
        # Inject the OR condition
        return f"(artist = {safe_val} OR artist_2 = {safe_val} OR artist_3 = {safe_val})"
    
    return ""

@frappe.whitelist()
def set_search_session(artist):
    # Update the cache
    frappe.cache().set_value(f"search_artist_{frappe.session.user}", artist)