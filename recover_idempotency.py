"""Reconcile interrupted webhook reservations before Uvicorn starts."""

from idempotency import recover_incomplete_webhook_deliveries


if __name__ == "__main__":
    recover_incomplete_webhook_deliveries()
