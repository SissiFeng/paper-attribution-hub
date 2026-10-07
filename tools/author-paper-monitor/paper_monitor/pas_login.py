"""Confirm a browser-bound PAS sign-in from an authenticated Slack command."""
import re
import time

from . import registry


def confirm(code, user, team, name):
    import hashlib
    code = code.strip().upper()
    if not re.fullmatch(r'[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}', code):
        raise ValueError('Open PAS first and copy its /papers login command into this private chat.')

    def approve(row):
        if row.get('expires', 0) <= time.time() or row.get('status') != 'pending' or not row.get('browser_hash'):
            raise ValueError('This PAS sign-in code expired or was already used. Start again on the PAS website.')
        row.update(status='verified', user_id=user, team_id=team, name=(name or user)[:160])

    registry.change('pas-login:' + hashlib.sha256(code.encode()).hexdigest(), approve)
