import frappe

def broadcast_raven_update(doc, method)
    event_name = "raven:unread_channel_count_updated"
    
    recipients = frappe.get_all(
        "Raven Channel Member",
        filters={"channel_id": doc.channel_id, "user_id": ["!=", doc.owner]},
        pluck="user_id"
    )

    for user in recipients:
        frappe.publish_realtime(event_name, {
            "channel_id": doc.channel_id,
            "sent_by": doc.owner,
            "last_message_timestamp": doc.creation
        }, user=user, after_commit=True)
        
        frappe.publish_realtime("play_raven_sound", user=user, after_commit=True)