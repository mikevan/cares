"""
Create the restricted database role the application should serve requests as.

WHY THIS IS A SEPARATE, MANUAL SCRIPT
-------------------------------------
Everything else in this codebase runs on startup. This does not, and must
not. The grants below are what stop the application's own credentials from
rewriting audit history or reading another council's ledger. If the
application could apply them, the application could re-apply them
differently -- and a control a process can grant itself is not a control.

So this is run once, deliberately, by whoever owns the database, using
credentials the running application does not have.

WHAT IT PRODUCES
----------------
A role with:
  - full SELECT/INSERT/UPDATE/DELETE on every business table
  - INSERT and SELECT ONLY on audit_log (no UPDATE, DELETE, TRUNCATE)
  - NO ownership of any table, so row-level security policies apply to it
  - NO SUPERUSER and NO BYPASSRLS

That last pair is the whole point and is verified before this script exits.

THE TWO-URL SPLIT
-----------------
    DATABASE_URL          owner. Runs migrations and DDL. Not used to
                          serve requests in production.
    RUNTIME_DATABASE_URL  this role. Serves requests. Subject to every
                          policy and every REVOKE.

app.py uses RUNTIME_DATABASE_URL when it is set and DATABASE_URL when it is
not, so a development machine keeps working with no configuration at all
and a production deployment that forgets to set it is refused at startup
rather than silently downgraded.

USAGE
-----
    python setup_runtime_role.py --role cares_app --password '<generated>'
    python setup_runtime_role.py --role cares_app          # prompts

Re-running it is safe: the role's password is updated and the grants are
re-applied. It never drops anything.
"""
import argparse
import getpass
import os
import sys

from sqlalchemy import create_engine, text
from sqlalchemy.exc import ProgrammingError

from audit_schema import grant_restricted_runtime_role
from services.security_check import verify_runtime_security, format_report


def _redact(url):
    """A connection URL is going in a terminal and probably a scrollback
    buffer. The password does not need to be in either."""
    if '@' not in url or '://' not in url:
        return url
    scheme, rest = url.split('://', 1)
    creds, host = rest.rsplit('@', 1)
    user = creds.split(':', 1)[0]
    return f'{scheme}://{user}:********@{host}'


def main():
    parser = argparse.ArgumentParser(
        description='Create the restricted runtime database role for CARES.')
    parser.add_argument('--role', default='cares_app',
                        help='Role name to create or update (default: cares_app)')
    parser.add_argument('--password', default=None,
                        help='Password for the role. Prompted for if omitted, '
                             'which keeps it out of your shell history.')
    parser.add_argument('--admin-url', default=None,
                        help='Owner connection URL. Defaults to $DATABASE_URL.')
    args = parser.parse_args()

    admin_url = args.admin_url or os.environ.get('DATABASE_URL')
    if not admin_url:
        print('ERROR: no --admin-url and no DATABASE_URL in the environment.')
        return 1

    password = args.password or getpass.getpass(f'Password for role {args.role}: ')
    if not password:
        print('ERROR: an empty password would create a role anyone can use.')
        return 1

    print(f'\nConnecting as owner: {_redact(admin_url)}')
    engine = create_engine(admin_url)
    try:
        with engine.begin() as connection:
            # DDL and GRANT both take locks. Fail in 15 seconds with a
            # message rather than blocking forever with none -- Postgres
            # reports nothing at all while it waits.
            connection.execute(text("SET LOCAL lock_timeout = '15s'"))
            grant_restricted_runtime_role(connection, args.role, password)

            # grant_restricted_runtime_role() enumerates the tables that
            # existed when it was written. Anything added since -- and this
            # schema has grown -- would be invisible to the new role, which
            # surfaces as a confusing permission error at runtime rather
            # than here. Cover the schema as it actually is, then re-apply
            # the audit_log restriction so the broad grant cannot undo it.
            role = _quote(args.role)
            connection.execute(text(
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}'))
            connection.execute(text(
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}'))
            connection.execute(text(f'REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM {role}'))

            # And cover tables that do not exist yet, so the next migration
            # to add one does not silently break this role.
            connection.execute(text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}'))
            connection.execute(text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT USAGE, SELECT ON SEQUENCES TO {role}'))

            # Belt and braces: neither attribute is granted above, but a
            # pre-existing role of the same name might carry them.
            #
            # Only a SUPERUSER may set or clear the SUPERUSER and BYPASSRLS
            # attributes -- even to values a role already holds. On every
            # managed Postgres (Render, RDS, Cloud SQL, Neon, Azure) the
            # owning role is not a superuser, so this ALTER is refused; and
            # because it runs inside engine.begin(), an unguarded failure
            # rolls back the role and every grant above it.
            #
            # So attempt it in a savepoint, and if it is refused for want of
            # privilege, VERIFY the two attributes instead of asserting them.
            # That is stronger, not weaker: it checks what is actually true
            # of the role rather than trusting that a statement did what it
            # claimed. A role created by a non-superuser cannot carry either
            # attribute, so the normal path passes; a pre-existing role that
            # does carry one is named and refused, which is the case the
            # belt-and-braces line existed for.
            try:
                with connection.begin_nested():
                    connection.execute(text(f'ALTER ROLE {role} NOSUPERUSER NOBYPASSRLS'))
            except ProgrammingError as exc:
                if 'permission denied' not in str(exc).lower():
                    raise
                print('   ALTER ROLE refused (this connection is not a superuser)'
                      ' -- verifying the attributes directly instead.')

            attributes = connection.execute(text(
                'SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :name'
            ), {'name': args.role}).first()
            if attributes is None:
                raise RuntimeError(
                    f'role {args.role} does not exist after creation -- refusing to '
                    f'report success.')
            if attributes.rolsuper or attributes.rolbypassrls:
                held = ' and '.join(
                    name for name, flag in (('SUPERUSER', attributes.rolsuper),
                                            ('BYPASSRLS', attributes.rolbypassrls)) if flag)
                raise RuntimeError(
                    f'role {args.role} holds {held}, and this connection cannot clear '
                    f'it. Row-level security policies would not apply to the '
                    f'application, and app.py would refuse to serve in production. '
                    f'Drop and recreate the role, or clear the attribute as a '
                    f'superuser, then run this again.')
        print(f'OK Role {args.role} created/updated and granted.')
    except Exception as e:
        print(f'\nERROR: could not create the role: {e}')
        return 1
    finally:
        engine.dispose()

    # ---- prove it, from the new role's own connection --------------------
    runtime_url = _swap_credentials(admin_url, args.role, password)
    print(f'\nVerifying as: {_redact(runtime_url)}')
    check_engine = create_engine(runtime_url)
    try:
        with check_engine.connect() as connection:
            report = verify_runtime_security(connection)
    except Exception as e:
        print(f'ERROR: the new role could not connect: {e}')
        print('Check pg_hba.conf allows password authentication for this role.')
        return 1
    finally:
        check_engine.dispose()

    print(format_report(report))
    if not report['secure']:
        print('\nThe role was created but does NOT provide the protections above.')
        print('Do not put this URL into RUNTIME_DATABASE_URL until it does.')
        return 1

    print('\nSet this on the application (NOT on whatever runs migrations):')
    print(f'\n    RUNTIME_DATABASE_URL={runtime_url}\n')
    print('Keep DATABASE_URL pointed at the owner role; migrate_production.py')
    print('needs it for DDL. The application will refuse to start in production')
    print('if RUNTIME_DATABASE_URL is missing or points at a privileged role.')
    return 0


def _quote(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def _swap_credentials(url, username, password):
    from urllib.parse import quote
    scheme, rest = url.split('://', 1)
    host = rest.rsplit('@', 1)[1] if '@' in rest else rest
    return f'{scheme}://{quote(username)}:{quote(password)}@{host}'


if __name__ == '__main__':
    sys.exit(main())
