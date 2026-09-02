"""Every blueprint in the package is in the registry both apps use.

`app.py` and `tests/conftest.py` used to keep separate hand-maintained lists of
blueprints to register. Adding one to production and not to the fixture broke
42 tests across members, projects and transactions — none of which had anything
to do with the new blueprint. The failure was a BuildError raised inside
base.html, so nothing in the output pointed at the actual mistake.

Both now call blueprints.register_blueprints(). This test closes the remaining
hole: a blueprint added to the package but never added to the registry.
"""

import ast
import glob
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from flask import Flask  # noqa: E402

from blueprints import register_blueprints  # noqa: E402

BLUEPRINTS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '..', '..', 'blueprints')
)


def _blueprint_names_defined_in_package():
    """Scan the source for `x = Blueprint('name', ...)` at module level."""
    names = set()
    for path in glob.glob(os.path.join(BLUEPRINTS_DIR, '*.py')):
        if os.path.basename(path) == '__init__.py':
            continue
        tree = ast.parse(open(path, encoding='utf-8').read())
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
                continue
            func = node.value.func
            if getattr(func, 'id', None) != 'Blueprint':
                continue
            if node.value.args and isinstance(node.value.args[0], ast.Constant):
                names.add(node.value.args[0].value)
    return names


def _registered_names():
    app = Flask(__name__)
    register_blueprints(app)
    return set(app.blueprints)


def test_every_blueprint_in_the_package_is_registered():
    defined = _blueprint_names_defined_in_package()
    registered = _registered_names()
    missing = defined - registered
    assert not missing, (
        'These blueprints exist but register_blueprints() does not register them, '
        'so they are absent from the app the tests build: %s' % sorted(missing)
    )


def test_the_registry_does_not_name_blueprints_that_do_not_exist():
    assert not (_registered_names() - _blueprint_names_defined_in_package())


def test_the_scan_actually_found_something():
    """Guard the guard: a broken scanner would make the test above vacuous."""
    assert len(_blueprint_names_defined_in_package()) >= 10


def test_registering_twice_on_one_app_is_not_silently_tolerated():
    """Two registrations would mean two lists again, and Flask says so."""
    app = Flask(__name__)
    register_blueprints(app)
    try:
        register_blueprints(app)
    except ValueError:
        return
    raise AssertionError('expected Flask to reject a duplicate blueprint registration')
