// Enhance the native Desk bell without replacing Frappe's notification handlers.
(() => {
	function setup() {
		const button = document.querySelector(".navbar .dropdown-notifications .notifications-icon");
		if (!button || button.querySelector(".cm-notification-count")) return;

		const badge = document.createElement("span");
		badge.className = "cm-notification-count";
		badge.hidden = true;
		badge.setAttribute("aria-hidden", "true");
		button.appendChild(badge);
		const status = document.createElement("span");
		status.className = "sr-only";
		status.setAttribute("role", "status");
		status.setAttribute("aria-live", "polite");
		button.appendChild(status);

		let timer;
		let revision = 0;
		function schedule_refresh() {
			revision += 1;
			clearTimeout(timer);
			timer = setTimeout(refresh, 150);
		}

		async function refresh() {
			if (document.hidden) return;
			const requested_revision = revision;
			try {
				const count = await frappe.db.count("Notification Log", {
					filters: { for_user: frappe.session.user, read: 0 },
				});
				// A newer event may have arrived while this request was in flight.
				if (requested_revision !== revision) return;
				const label = count
					? __("{0} unread notifications", [count])
					: __("No unread notifications");
				badge.textContent = count > 99 ? "99+" : String(count);
				badge.hidden = !count;
				button.classList.toggle("cm-has-unread", count > 0);
				button.setAttribute("aria-label", label);
				button.setAttribute("title", label);
				button.setAttribute("data-original-title", label);
				if (status.textContent !== label) status.textContent = label;
			} catch (error) {
				// Preserve the last known count; reconnect/focus/periodic refresh retries.
				console.debug("Unable to refresh notification count", error);
			}
		}

		frappe.realtime.on("notification", schedule_refresh);
		frappe.realtime.on("indicator_hide", schedule_refresh);
		frappe.realtime.on("connect", schedule_refresh);
		// Refresh after successful native read actions, which do not emit realtime events.
		$(document).on("ajaxSuccess.cmNotificationBadge", (_event, xhr, settings) => {
			const method = "frappe.desk.doctype.notification_log.notification_log.";
			const command = typeof settings.data === "string"
				? new URLSearchParams(settings.data).get("cmd")
				: settings.data?.cmd;
			if (["mark_as_read", "mark_all_as_read"].some((action) =>
				command === method + action || settings.url?.split("?")[0].endsWith("/" + method + action)
			) && !xhr.responseJSON?.exc) schedule_refresh();
		});
		window.addEventListener("focus", schedule_refresh);
		document.addEventListener("visibilitychange", schedule_refresh);
		// Also reconcile changes made in another tab or from the full Notification Log.
		setInterval(schedule_refresh, 60000);
		schedule_refresh();
	}

	$(document).on("app_ready", setup);
	$(setup);
})();
