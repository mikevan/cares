"""
Shared Flask extension instances.

Created here (uninitialized) and bound to the app with .init_app() in
app.py, following the same pattern already used for `db` in models.py --
this lets blueprints import and use `limiter` without a circular import
back to app.py.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Per-remote-address by default. A whole council office behind one NAT'd
# IP shares a quota, which is a deliberate, generous trade-off for a small
# nonprofit deployment -- see the limit applied to auth_routes.login().
limiter = Limiter(key_func=get_remote_address)
