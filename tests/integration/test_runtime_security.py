"""
Proof that organization isolation and audit immutability actually hold.

Every other test in this suite runs as the table owner, which bypasses every
row-level security policy. That makes them useless for verifying isolation:
they would pass identically against a database with no policies at all.

So these tests create the restricted runtime role, connect through it, and
assert on what that connection can and cannot do. If the policies are
missing, mis-scoped, or silently inert, these fail. Nothing else in the
suite would.

WHY RAW SQL AND A SEPARATE ENGINE
---------------------------------
The ORM session in `db_session` is the owner's, wrapped in an outer
transaction that rolls back at teardown. Reusing it would test the wrong
role. Each test here opens its own engine as the restricted role, and
anything it needs to see must be COMMITTED by the owner first -- a different
connection cannot read another connection's uncommitted rows.

That committed data is cleaned up explicitly, because it is outside the
harness's rollback.

THE ADVISORY-LOCK TRAP
----------------------
Writes from the restricted connection fire the audit trigger, which takes
`pg_advisory_xact_lock('cares_audit_log_chain', <org>)`. If this test's
own outer session is holding that same organization's lock from an
uncommitted write, the two connections deadlock -- the test cannot finish
until teardown and teardown cannot run until the test finishes. This is
not hypothetical; it is documented at test_audit_trail.py's restricted-role
test, which hit exactly this. These tests therefore commit before switching
connections and never mix the two roles inside one organization's chain.
"""
import pytest
from sqlalchemy import create_engine, text

from models import db
from audit_schema import grant_restricted_runtime_role, AUDITED_TABLES
from rls_schema import (
    install_rls, DIRECT_ORG_TABLES, DERIVED_ORG_TABLES, UNPROTECTED_TABLES,
)
from services.security_check import verify_runtime_security

RESTRICTED_ROLE = 'test_cares_rls_role'
RESTRICTED_PW = 'test_pw_rls_4482'


@pytest.fixture(scope='session')
def restricted_engine(app):
    """An engine connected as a role that RLS actually applies to.

    SESSION-scoped, and that is not an optimization. Installing the policies
    requires ACCESS EXCLUSIVE locks, taken on a second connection. The
    harness's function-scoped `db_session` fixture is autouse and holds an
    open transaction for the length of every test, so a function-scoped
    version of this fixture would queue behind locks that are not released
    until the test it is running inside has finished. Pytest sets up
    higher-scoped fixtures first, so at session scope the DDL runs before
    any `db_session` exists.

    Third occurrence of this pattern in the codebase. `lock_timeout` below
    is the seatbelt: if it is ever wrong again it fails in fifteen seconds
    with a message instead of hanging the suite with none.
    """
    with app.app_context():
        owner_url = db.engine.url
        with db.engine.begin() as connection:
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            install_rls(connection, verbose=False)
            grant_restricted_runtime_role(connection, RESTRICTED_ROLE, RESTRICTED_PW)
            role = f'"{RESTRICTED_ROLE}"'
            connection.execute(text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}'))
            connection.execute(text(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))
            connection.execute(text(
                f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {role}'))
            connection.execute(text(f'ALTER ROLE {role} NOSUPERUSER NOBYPASSRLS'))

        engine = create_engine(owner_url.set(
            username=RESTRICTED_ROLE, password=RESTRICTED_PW))
        try:
            yield engine
        finally:
            engine.dispose()


@pytest.fixture(scope='function')
def two_councils(app):
    """Two committed organizations, each with one project and one member.

    Committed deliberately -- the restricted connection is a different
    connection and cannot see uncommitted rows. Cleaned up in reverse
    dependency order afterwards, since the harness's rollback does not cover
    committed work.
    """
    with app.app_context():
        with db.engine.begin() as connection:
            # These INSERTs fire the audit trigger, which takes the chain
            # advisory lock. If the harness's outer session is holding it
            # from an uncommitted write, fail in seconds rather than
            # deadlocking the suite.
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            rows = {}
            for label in ('alpha', 'bravo'):
                org_id = connection.execute(text(
                    "INSERT INTO organizations (name, org_type) "
                    "VALUES (:name, 'Chapter') RETURNING id"
                ), {'name': f'RLS Test Council {label}'}).scalar()
                project_id = connection.execute(text(
                    "INSERT INTO projects (name, organization_id, status) "
                    "VALUES (:name, :org, 'Active') RETURNING id"
                ), {'name': f'Project {label}', 'org': org_id}).scalar()
                member_id = connection.execute(text(
                    "INSERT INTO members (name, organization_id, active) "
                    "VALUES (:name, :org, true) RETURNING id"
                ), {'name': f'{label.capitalize()} Testcouncil', 'org': org_id}).scalar()
                rows[label] = {'org_id': org_id, 'project_id': project_id,
                               'member_id': member_id}
        try:
            yield rows
        finally:
            with db.engine.begin() as connection:
                ids = [r['org_id'] for r in rows.values()]
                for table in ('members', 'projects'):
                    connection.execute(
                        text(f'DELETE FROM {table} WHERE organization_id = ANY(:ids)'),
                        {'ids': ids})
                connection.execute(
                    text('DELETE FROM organizations WHERE id = ANY(:ids)'), {'ids': ids})


def _model_table_names():
    """Every table SQLAlchemy actually knows about, from the mapper registry
    rather than a hand-maintained list -- the point of these two tests is to
    catch a table nobody remembered to mention anywhere."""
    return {mapper.class_.__tablename__
            for mapper in db.Model.registry.mappers
            if hasattr(mapper.class_, '__tablename__')}


def _as_council(engine, org_id, scope=None):
    """A connection with tenant context set the way app.py sets it."""
    conn = engine.connect()
    conn.execute(text("SET app.current_organization_id = :o"), {'o': str(org_id)})
    conn.execute(text("SET app.current_organization_scope = :s"),
                 {'s': ','.join(str(i) for i in (scope or [org_id]))})
    return conn


@pytest.mark.integration
class TestOrganizationIsolationIsEnforced:

    def test_a_council_sees_only_its_own_members(self, restricted_engine, two_councils):
        alpha, bravo = two_councils['alpha'], two_councils['bravo']
        conn = _as_council(restricted_engine, alpha['org_id'])
        try:
            visible = {r[0] for r in conn.execute(text(
                "SELECT id FROM members WHERE name LIKE '%Testcouncil'")).fetchall()}
        finally:
            conn.close()
        assert alpha['member_id'] in visible
        assert bravo['member_id'] not in visible, (
            "council alpha read council bravo's member roster -- the isolation "
            "policy is not in force"
        )

    def test_a_council_cannot_read_another_councils_rows_even_by_primary_key(
            self, restricted_engine, two_councils):
        """The failure this replaces was a missing WHERE clause, so the test
        that matters is the one where the query names the other council's row
        explicitly and still gets nothing."""
        alpha, bravo = two_councils['alpha'], two_councils['bravo']
        conn = _as_council(restricted_engine, alpha['org_id'])
        try:
            row = conn.execute(text("SELECT id FROM projects WHERE id = :id"),
                               {'id': bravo['project_id']}).first()
        finally:
            conn.close()
        assert row is None, (
            "a direct primary-key lookup crossed the tenant boundary -- this is "
            "the exact shape of the V1 authorization bugs RLS exists to backstop"
        )

    def test_no_tenant_context_returns_nothing_rather_than_everything(
            self, restricted_engine, two_councils):
        """Failing closed is the whole point. A background job that forgets to
        set context must see an empty database, not every council's books."""
        conn = restricted_engine.connect()
        try:
            count = conn.execute(text(
                "SELECT count(*) FROM members WHERE name LIKE '%Testcouncil'")).scalar()
        finally:
            conn.close()
        assert count == 0

    def test_a_council_cannot_write_into_another_councils_books(
            self, restricted_engine, two_councils):
        alpha, bravo = two_councils['alpha'], two_councils['bravo']
        conn = _as_council(restricted_engine, alpha['org_id'])
        try:
            with pytest.raises(Exception) as excinfo:
                conn.execute(text(
                    "INSERT INTO members (name, organization_id, active) "
                    "VALUES ('Intruder Testcouncil', :org, true)"
                ), {'org': bravo['org_id']})
                conn.commit()
            assert 'policy' in str(excinfo.value).lower()
        finally:
            conn.rollback()
            conn.close()


@pytest.mark.integration
class TestHierarchyScope:

    def test_a_parent_reads_its_children_but_cannot_post_to_them(
            self, restricted_engine, two_councils, app):
        """The state-deputy case: roll-up reporting must work, posting must not.

        A council's trustees sign its ledger under Section 145, so an entry in
        that ledger has to have been made by someone inside the council.
        """
        alpha, bravo = two_councils['alpha'], two_councils['bravo']
        with app.app_context():
            with db.engine.begin() as connection:
                connection.execute(
                    text("UPDATE organizations SET parent_id = :p WHERE id = :c"),
                    {'p': alpha['org_id'], 'c': bravo['org_id']})

        conn = _as_council(restricted_engine, alpha['org_id'],
                           scope=[alpha['org_id'], bravo['org_id']])
        try:
            visible = {r[0] for r in conn.execute(text(
                "SELECT id FROM members WHERE name LIKE '%Testcouncil'")).fetchall()}
            assert bravo['member_id'] in visible, "a parent must be able to roll up its children"

            with pytest.raises(Exception) as excinfo:
                conn.execute(text(
                    "INSERT INTO projects (name, organization_id, status) "
                    "VALUES ('Posted From Above', :org, 'Active')"
                ), {'org': bravo['org_id']})
                conn.commit()
            assert 'policy' in str(excinfo.value).lower(), (
                "read scope must not become write scope -- WITH CHECK is what "
                "keeps a state body out of a council's ledger"
            )
        finally:
            conn.rollback()
            conn.close()

    def test_scope_wider_than_read_access_still_cannot_widen_writes(
            self, restricted_engine, two_councils):
        """Guards the obvious attack on a session-set scope: claim everything.

        Even a connection declaring the whole world in scope writes only to
        current_org(), because WITH CHECK reads that and not the scope.
        """
        alpha, bravo = two_councils['alpha'], two_councils['bravo']
        conn = _as_council(restricted_engine, alpha['org_id'],
                           scope=[alpha['org_id'], bravo['org_id']])
        try:
            with pytest.raises(Exception):
                conn.execute(text(
                    "INSERT INTO members (name, organization_id, active) "
                    "VALUES ('Wide Testcouncil', :org, true)"
                ), {'org': bravo['org_id']})
                conn.commit()
        finally:
            conn.rollback()
            conn.close()


@pytest.mark.integration
class TestAuditLogImmutability:

    def test_the_runtime_role_cannot_alter_audit_history(self, restricted_engine):
        conn = restricted_engine.connect()
        try:
            for statement in ("UPDATE audit_log SET operation = 'INSERT'",
                              "DELETE FROM audit_log",
                              "TRUNCATE audit_log"):
                with pytest.raises(Exception):
                    conn.execute(text(statement))
                    conn.commit()
                conn.rollback()
        finally:
            conn.close()

    def test_the_security_check_agrees_with_reality(self, restricted_engine):
        """The check exists so operators do not have to run the above by hand.
        If it and the database ever disagree, the check is worse than useless."""
        conn = restricted_engine.connect()
        try:
            report = verify_runtime_security(conn)
        finally:
            conn.close()
        assert report['role_name'] == RESTRICTED_ROLE
        assert report['rls_enforced'] is True
        assert report['audit_log_immutable'] is True
        assert report['secure'] is True, report['findings']

    def test_the_security_check_fails_the_owner_connection(self, app):
        """The negative case, and the one that actually matters: the default
        single-URL configuration must be reported as NOT secure."""
        with app.app_context():
            with db.engine.connect() as connection:
                report = verify_runtime_security(connection)
        assert report['secure'] is False
        assert report['findings'], "an insecure connection must say why"


@pytest.mark.integration
class TestTenancyCoverage:

    def test_every_table_has_a_deliberate_tenancy_decision(self):
        """A new table must not be able to join the schema without someone
        deciding whether it is tenant-scoped.

        This is the test that ages well. The policies are correct today; the
        way this regresses is a model added six months from now that nobody
        thinks about, and RLS's fail-closed default means the symptom will be
        an empty screen rather than a leak -- but only if it is in a list.
        """
        declared = set(DIRECT_ORG_TABLES) \
            | {t[0] for t in DERIVED_ORG_TABLES} \
            | set(UNPROTECTED_TABLES)
        actual = _model_table_names()
        missing = actual - declared
        assert not missing, (
            f"tables missing from rls_schema.py: {sorted(missing)} -- add each to "
            f"DIRECT_ORG_TABLES, DERIVED_ORG_TABLES or UNPROTECTED_TABLES with a "
            f"reason"
        )
        stale = declared - actual
        assert not stale, f"rls_schema.py lists tables that no longer exist: {sorted(stale)}"

    def test_every_audited_table_exists(self):
        stale = set(AUDITED_TABLES) - _model_table_names()
        assert not stale, f"AUDITED_TABLES lists tables that do not exist: {sorted(stale)}"
