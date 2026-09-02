"""
Blueprint registry.

`app.py` and `tests/conftest.py` both build a Flask application, and they used
to register blueprints from two hand-maintained lists. That drifts, and it
drifted the moment a blueprint was added: `base.html` gained a `url_for()` to
an endpoint the test fixture had never registered, and 42 tests failed with
BuildError inside templates that had nothing to do with the new feature.

The failure was loud, but it was loud in the wrong place — the tests that broke
were about members, projects and transactions. Nothing pointed at the actual
mistake, which was a list in a fixture that nobody thinks to update.

So there is one list now, and both callers use it. A blueprint registered for
production is registered for the tests by construction.

(The same drift exists for request hooks — conftest mirrors `app.py`'s
`before_request`/`teardown_request` handlers by hand, and missing
`apply_tenant_context` is why the suite could not catch the tenant-context bug
found during the Render deployment. That one is still outstanding; see the
deployment record. This fixes the blueprint half.)
"""


def register_blueprints(app):
    """Register every application blueprint on `app`.

    Imports are inside the function on purpose: this module is
    `blueprints/__init__.py`, so importing the submodules at module scope would
    run on every `from blueprints.x import y` anywhere in the codebase.
    """
    from blueprints.auth_routes import auth_bp
    from blueprints.member_routes import members_bp
    from blueprints.user_routes import users_bp
    from blueprints.chart_of_accounts import chart_of_accounts_bp
    from blueprints.transaction_routes import transactions_bp
    from blueprints.project_routes import projects_bp
    from blueprints.report_routes import reports_bp
    from blueprints.settings_routes import settings_bp
    from blueprints.ap_routes import ap_bp
    from blueprints.audit_routes import audit_bp
    from blueprints.translation_admin_routes import translation_admin_bp

    for blueprint in (
        auth_bp,
        members_bp,
        users_bp,
        chart_of_accounts_bp,
        transactions_bp,
        projects_bp,
        reports_bp,
        settings_bp,
        ap_bp,
        audit_bp,
        translation_admin_bp,
    ):
        app.register_blueprint(blueprint)

    return app
