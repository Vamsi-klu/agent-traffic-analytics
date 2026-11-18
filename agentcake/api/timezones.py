"""GET /api/timezones: the time zones the settings page lists for the setting `timezone`, as PostHog's time zone
setting lists its project's (posthog/api/preflight.py available_timezones, offsets from
posthog/utils.py get_available_timezones_with_offsets; MIT, no code copied).

    zones   [{"name", "label"}]: UTC, then IANA's zone.tab zones the timezone database knows, each labelled with its
            offset from UTC now (timezone.listed): "America / Los Angeles (UTC-08:00)"
"""
from agentcake import timezone
from agentcake.api import answers, periods


@answers.view
def view(request):
    return answers.ok({"zones": timezone.listed(periods.now_ms())})
