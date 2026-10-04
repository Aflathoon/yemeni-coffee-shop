"""
Custom wholesale session helpers.

Wholesale accounts do NOT use Flask-Login. They're identified by an
integer ID stored in the Flask session under 'ws_id'. This keeps the
retail and wholesale login systems fully independent.
"""
from functools import wraps
from flask import session, redirect, url_for, flash, g, request
from app.models import WholesaleAccount


SESSION_KEY = "ws_id"


def login_wholesale(account):
    """Mark a wholesale account as signed in."""
    session[SESSION_KEY] = account.id
    session.permanent = True


def logout_wholesale():
    """Sign out the current wholesale account."""
    session.pop(SESSION_KEY, None)


def current_wholesale():
    """
    Return the current WholesaleAccount or None.
    Cached on flask.g for the duration of a request.
    """
    if "_current_wholesale" in g:
        return g._current_wholesale
    ws_id = session.get(SESSION_KEY)
    if not ws_id:
        g._current_wholesale = None
        return None
    acct = WholesaleAccount.query.get(ws_id)
    g._current_wholesale = acct
    return acct


def is_wholesale_logged_in():
    return current_wholesale() is not None


def wholesale_required(f):
    """Decorator: require a signed-in wholesale account."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if not is_wholesale_logged_in():
            flash("Please sign in to your partner account.", "error")
            return redirect(url_for("wholesale.login", next=request.path))
        return f(*args, **kwargs)
    return decorated


def approved_wholesale_required(f):
    """Decorator: require a signed-in AND approved wholesale account."""
    @wraps(f)
    def decorated(*args, **kwargs):
        acct = current_wholesale()
        if not acct:
            flash("Please sign in to your partner account.", "error")
            return redirect(url_for("wholesale.login", next=request.path))
        if not acct.is_approved:
            flash("Your account is not yet approved for wholesale ordering.", "warning")
            return redirect(url_for("wholesale.dashboard"))
        return f(*args, **kwargs)
    return decorated
