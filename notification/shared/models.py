from dataclasses import dataclass


@dataclass
class NotificationPayload:
    """Strictly typed data model for the SQS message body."""

    email: str
    planning_area: str
    risk_level: str
