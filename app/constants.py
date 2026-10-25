"""Fixed values used across FixFlow."""

CATEGORIES = ["plumbing", "electrical", "cleaning", "carpentry", "general"]

URGENCY_LEVELS = ["low", "medium", "high", "emergency"]

STATUS_REPORTED = "Reported"
STATUS_ASSIGNED = "Assigned"
STATUS_IN_PROGRESS = "In Progress"
STATUS_RESOLVED = "Resolved"

STATUSES = [STATUS_REPORTED, STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_RESOLVED]

# Which status changes are allowed through the manual status endpoint.
# "Assigned" is deliberately NOT reachable here: it only happens after human approval.
ALLOWED_STATUS_TRANSITIONS = {
    STATUS_REPORTED: [],
    STATUS_ASSIGNED: [STATUS_IN_PROGRESS],
    STATUS_IN_PROGRESS: [STATUS_RESOLVED],
    STATUS_RESOLVED: [],
}
