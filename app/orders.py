"""Order lifecycle helpers — status changes with audit trail."""
from datetime import datetime
from app import db
from app.models import Order, OrderEvent


VALID_TRANSITIONS = {
    "pending":   ["paid", "cancelled"],
    "paid":      ["shipped", "cancelled"],
    "shipped":   ["delivered", "cancelled"],
    "delivered": [],
    "cancelled": [],
}


def change_order_status(order, new_status, actor_email=None, actor_role="admin",
                        note=None, tracking_number=None, courier=None,
                        cancellation_reason=None, cancelled_by=None):
    """
    Move an order to a new status. Validates the transition, stamps the
    appropriate timestamp, and writes an OrderEvent.

    Returns (ok: bool, error_message or None).
    """
    old_status = order.status
    if old_status == new_status:
        return False, f"Order is already {new_status}"

    if new_status not in VALID_TRANSITIONS.get(old_status, []):
        return False, f"Cannot move from {old_status} to {new_status}"

    now = datetime.utcnow()

    # Stamp the right timestamp
    if new_status == "paid":
        order.paid_at = now
    elif new_status == "shipped":
        order.shipped_at = now
        if tracking_number:
            order.tracking_number = tracking_number
        if courier:
            order.courier = courier
    elif new_status == "delivered":
        order.delivered_at = now
    elif new_status == "cancelled":
        order.cancelled_at = now
        order.cancelled_by = cancelled_by or actor_role
        order.cancellation_reason = cancellation_reason or note

    order.status = new_status

    # Log the event
    db.session.add(OrderEvent(
        order_id=order.id,
        event_type="status_change",
        from_status=old_status,
        to_status=new_status,
        note=note,
        actor_email=actor_email,
        actor_role=actor_role,
    ))
    db.session.commit()

    # Fire-and-forget email notification
    try:
        from app.mail import send_order_status_update
        send_order_status_update(order, new_status)
    except Exception:
        pass   # never block the state change on email failure

    return True, None
