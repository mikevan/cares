"""Fix the Step 7 self-deadlock in migrate_production.install_row_level_security().

Same defect as the demo loader's "Preparing the audit trail" hang, and the
same defect noted in the V2 backlog under audit trail follow-ups. Third
occurrence:

    connection A (db.session)   holds ACCESS SHARE on organizations,
                                chart_of_accounts, projects, ... from the
                                queries the earlier migration steps ran and
                                never committed.

    connection B (db.engine.begin())  asks for ACCESS EXCLUSIVE to run
                                ALTER TABLE ... ENABLE ROW LEVEL SECURITY
                                and CREATE TRIGGER.

B waits on A. A is idle-in-transaction inside the same process, waiting for
B to return. Postgres does not detect this as a deadlock because it is not
one -- it is one transaction politely waiting forever for another that will
never commit. No error is raised, which is why it reads as a hang.

Two changes, both of which independently prevent it:

  1. Run the DDL on db.session's OWN connection instead of a second one.
     A transaction cannot block itself; the locks it already holds are its
     own to upgrade. This is the actual fix.

  2. Set lock_timeout first. If any OTHER session ever holds a conflicting
     lock -- a psql window left open, a second app worker -- the migration
     now fails in 15 seconds with a message naming the problem, instead of
     hanging with no output. Blocking is not failure in Postgres, so
     anything taking ACCESS EXCLUSIVE has to say how long it is willing to
     wait.
"""
import io

p = 'migrate_production.py'
s = io.open(p, 'r', encoding='utf-8', newline='').read()
NL = '\r\n' if '\r\n' in s else '\n'


def fit(t):
    return NL.join(t.strip('\n').split('\n'))


OLD = fit('''
    default_org = Organization.query.order_by(Organization.id).first()
    if default_org is None:
        print("  ! No organization exists yet; skipping")
        return
    try:
        with db.engine.begin() as connection:
            install_rls(connection)
            backfill_organization_ids(connection, default_org.id)
        with db.engine.connect() as connection:
            report = verify_isolation(connection)
''')
assert OLD in s, 'install_row_level_security body not found -- was it already patched?'

NEW = fit('''
    default_org = Organization.query.order_by(Organization.id).first()
    if default_org is None:
        print("  ! No organization exists yet; skipping")
        return

    # Release every lock the earlier migration steps are still holding
    # before asking for ACCESS EXCLUSIVE. Their reads left this session
    # idle-in-transaction; without this commit the DDL below would queue
    # behind locks held by the very session issuing it.
    db.session.commit()

    try:
        # db.session's own connection -- NOT db.engine.begin(), which opens a
        # second one that then waits on the first. See this file's history:
        # the demo loader hung the same way on DROP TRIGGER.
        connection = db.session.connection()

        # Fail loudly rather than silently, if some OTHER session (a psql
        # window, a second worker) holds a conflicting lock. Postgres blocks
        # indefinitely by default and reports nothing while it does.
        connection.execute(text("SET LOCAL lock_timeout = '15s'"))

        install_rls(connection)
        backfill_organization_ids(connection, default_org.id)
        report = verify_isolation(connection)
        db.session.commit()
''')
s = s.replace(OLD, NEW, 1)

# The except block must now roll back the session it just used.
OLD_EXCEPT = fit('''
    except Exception as e:
        db.session.rollback()
        print(f"  ! Could not install row-level security: {e}")
''')
assert OLD_EXCEPT in s
NEW_EXCEPT = fit('''
    except Exception as e:
        db.session.rollback()
        if 'lock timeout' in str(e).lower() or 'canceling statement' in str(e).lower():
            print("  ! Timed out waiting for a table lock. Something else holds an")
            print("    open transaction on an audited table -- a psql session, a")
            print("    running app worker, or an idle connection. Close it and")
            print("    re-run; row-level security is not installed.")
        else:
            print(f"  ! Could not install row-level security: {e}")
''')
s = s.replace(OLD_EXCEPT, NEW_EXCEPT, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('patched', p)
