"""Read-only Phase 6 delivery timeline reconstructed from audit events."""

import uuid

from db import get_request_events


KNOWN_DELIVERY_EVENT_STAGES = {
    "delivery_handoff_activated": "handoff",
    "delivery_notifications_prepared": "notification_preparation",
    "delivery_appointment_proposed": "appointment",
    "delivery_appointment_confirmed": "appointment",
    "delivery_status_scheduled": "execution",
    "delivery_status_in_progress": "execution",
    "delivery_exception_recorded": "exception",
    "human_intervention_created": "intervention",
    "human_intervention_acknowledged": "intervention",
    "delivery_status_completed": "completion",
}


class DeliveryTimelineValidationError(ValueError):
    pass


def _validate_uuid(value, field_name):
    if not isinstance(value, uuid.UUID):
        raise DeliveryTimelineValidationError(
            f"{field_name} must be a UUID"
        )
    return value


def _is_delivery_event(event_type):
    return (
        event_type.startswith("delivery_")
        or event_type.startswith("human_intervention_")
    )


def get_delivery_timeline(request_id):
    request_id = _validate_uuid(request_id, "request_id")
    events = [
        event
        for event in get_request_events(request_id)
        if _is_delivery_event(event["event_type"])
    ]

    timeline = []
    for sequence, event in enumerate(events, start=1):
        event_type = event["event_type"]
        timeline.append(
            {
                "sequence": sequence,
                "event_id": str(event["id"]),
                "event_type": event_type,
                "stage": KNOWN_DELIVERY_EVENT_STAGES.get(
                    event_type,
                    "delivery",
                ),
                "known_event_type": (
                    event_type in KNOWN_DELIVERY_EVENT_STAGES
                ),
                "actor": event["actor"],
                "details": dict(event["details"] or {}),
                "correlation_id": event["correlation_id"],
                "created_at": event["created_at"],
            }
        )

    return {
        "request_id": str(request_id),
        "event_count": len(timeline),
        "latest_stage": (
            None if not timeline else timeline[-1]["stage"]
        ),
        "delivery_completed": any(
            item["event_type"] == "delivery_status_completed"
            for item in timeline
        ),
        "has_exceptions": any(
            item["event_type"] == "delivery_exception_recorded"
            for item in timeline
        ),
        "has_interventions": any(
            item["event_type"].startswith("human_intervention_")
            for item in timeline
        ),
        "timeline": timeline,
    }
