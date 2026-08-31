"""Per-organization audit chains: trigger, verification, and the Procfile."""
import io
import re

# ===================================================== audit_schema.py
p = 'audit_schema.py'
s = io.open(p, 'r', encoding='utf-8', newline='').read()
NL = '\r\n' if '\r\n' in s else '\n'

NEW_TRIGGER = '''_TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION audit_trigger_fn() RETURNS TRIGGER AS $$
DECLARE
    v_old JSONB;
    v_new JSONB;
    v_row_id INTEGER;
    v_org_id INTEGER;
    v_user_id INTEGER;
    v_prev_hash TEXT;
    v_payload TEXT;
    v_row_hash TEXT;
    v_changed_at TIMESTAMPTZ;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_old := to_jsonb(OLD);
        v_new := NULL;
        v_row_id := (v_old->>'id')::INTEGER;
    ELSIF TG_OP = 'UPDATE' THEN
        v_old := to_jsonb(OLD);
        v_new := to_jsonb(NEW);
        v_row_id := (v_new->>'id')::INTEGER;
    ELSE
        v_old := NULL;
        v_new := to_jsonb(NEW);
        v_row_id := (v_new->>'id')::INTEGER;
    END IF;

    -- Which organization's chain this row belongs to, taken from the audited
    -- row itself rather than from session state: a row's owner is a property
    -- of the data, not of whoever happened to be connected. Tables with no
    -- organization of their own (users, organizations) share chain 0.
    BEGIN
        v_org_id := COALESCE(
            (v_new->>'organization_id')::INTEGER,
            (v_old->>'organization_id')::INTEGER
        );
    EXCEPTION WHEN others THEN
        v_org_id := NULL;
    END;

    -- Serialize per organization, not globally. The previous single lock
    -- meant every audited write in the deployment queued behind every other
    -- one -- so a council posting a 300-member dues roster in one
    -- transaction stalled every other council for its duration. At one
    -- council that is invisible; at a hundred it is the ceiling on the whole
    -- system. Two-argument advisory locks give each organization its own
    -- lock space while keeping the guarantee that matters: writes WITHIN a
    -- chain are still fully serialized, so that chain cannot fork.
    PERFORM pg_advisory_xact_lock(hashtext('cares_audit_log_chain'), COALESCE(v_org_id, 0));

    -- Captured once and reused for both the hash payload and the stored
    -- column below. clock_timestamp() is volatile -- calling it twice would
    -- give two slightly different values, which would make later hash
    -- verification fail on every single row.
    v_changed_at := clock_timestamp();

    -- Set by services/audit_context.py once per transaction. NULL here means
    -- either a background/maintenance script or -- more importantly -- a
    -- change that did not go through the application at all. That is itself
    -- useful evidence: a real trustee audit should treat a NULL actor on a
    -- production system as a change to ask about, not to ignore.
    BEGIN
        v_user_id := NULLIF(current_setting('app.current_user_id', true), '')::INTEGER;
    EXCEPTION WHEN others THEN
        v_user_id := NULL;
    END;

    -- The tail of THIS organization's chain. Each organization has its own
    -- genesis, so one council's history can be verified without reading any
    -- other council's rows -- which is what lets audit_log carry a row-level
    -- security policy at all.
    SELECT row_hash INTO v_prev_hash
      FROM audit_log
     WHERE organization_id IS NOT DISTINCT FROM v_org_id
     ORDER BY id DESC LIMIT 1;

    -- organization_id is inside the payload deliberately: without it, a row
    -- could be moved between chains after the fact and still hash correctly.
    v_payload := coalesce(v_prev_hash, '<genesis>') || '|' || TG_TABLE_NAME || '|' || TG_OP || '|'
                 || coalesce(v_org_id::text, '<none>') || '|'
                 || coalesce(v_old::text, '') || '|' || coalesce(v_new::text, '')
                 || '|' || coalesce(v_user_id::text, '<unknown>') || '|' || v_changed_at::text;
    v_row_hash := encode(digest(v_payload, 'sha256'), 'hex');

    INSERT INTO audit_log(table_name, row_id, organization_id, operation, old_data, new_data,
                           changed_by_user_id, db_role, changed_at, prev_hash, row_hash)
    VALUES (TG_TABLE_NAME, v_row_id, v_org_id, TG_OP, v_old, v_new, v_user_id, current_user,
            v_changed_at, v_prev_hash, v_row_hash);

    RETURN NULL; -- AFTER trigger; return value is ignored either way
END;
$$ LANGUAGE plpgsql;
"""'''

m = re.search(r'_TRIGGER_FUNCTION_SQL = """.*?"""', s, re.S)
assert m, 'trigger function constant not found'
s = s[:m.start()] + NEW_TRIGGER.replace('\n', NL) + s[m.end():]

# audit_log now needs the column before the trigger can write it.
anchor = 'def install_audit_triggers(connection):'
assert anchor in s
s = s.replace(anchor, (
    'def ensure_audit_log_organization_column(connection):' + NL +
    '    """audit_log.organization_id must exist before the trigger writes it.' + NL +
    NL +
    '    Also created by rls_schema.install_rls(); duplicated here so installing' + NL +
    '    the audit triggers alone cannot leave the trigger writing to a column' + NL +
    '    that is not there."""' + NL +
    '    connection.execute(text(' + NL +
    '        "ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS organization_id INTEGER"))' + NL +
    '    connection.execute(text(' + NL +
    '        "CREATE INDEX IF NOT EXISTS idx_audit_log_org_id ON audit_log(organization_id, id)"))' + NL +
    NL + NL + anchor), 1)

anchor2 = '    connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))'
assert anchor2 in s
s = s.replace(anchor2, anchor2 + NL + '    ensure_audit_log_organization_column(connection)', 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('audit_schema.py: per-organization chains')

# ===================================================== audit_routes.py
p = 'blueprints/audit_routes.py'
s = io.open(p, 'r', encoding='utf-8', newline='').read()
NL = '\r\n' if '\r\n' in s else '\n'

OLD_SELF = """        WHERE row_hash <> encode(digest(
            coalesce(prev_hash, '<genesis>') || '|' || table_name || '|' || operation || '|' ||
            coalesce(old_data::text, '') || '|' || coalesce(new_data::text, '') || '|' ||
            coalesce(changed_by_user_id::text, '<unknown>') || '|' || changed_at::text,
            'sha256'), 'hex')""".replace('\n', NL)
assert OLD_SELF in s, 'self-consistency query not found'
NEW_SELF = """        WHERE row_hash <> encode(digest(
            coalesce(prev_hash, '<genesis>') || '|' || table_name || '|' || operation || '|' ||
            coalesce(organization_id::text, '<none>') || '|' ||
            coalesce(old_data::text, '') || '|' || coalesce(new_data::text, '') || '|' ||
            coalesce(changed_by_user_id::text, '<unknown>') || '|' || changed_at::text,
            'sha256'), 'hex')""".replace('\n', NL)
s = s.replace(OLD_SELF, NEW_SELF, 1)

OLD_LAG = "                   lag(row_hash) OVER (ORDER BY id) AS expected_prev_hash".replace('\n', NL)
assert OLD_LAG in s, 'lag() window not found'
NEW_LAG = ("                   lag(row_hash) OVER (PARTITION BY organization_id ORDER BY id)" + NL +
           "                       AS expected_prev_hash")
s = s.replace(OLD_LAG, NEW_LAG, 1)

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('audit_routes.py: verification partitioned by organization')

# ===================================================== Procfile
p = 'Procfile'
s = io.open(p, 'r', encoding='utf-8', newline='').read()
assert 'gunicorn app:app' in s
io.open(p, 'w', encoding='utf-8', newline='').write(
    'web: gunicorn app:app --workers 4 --threads 2 --timeout 120\n')
print('Procfile: 4 workers x 2 threads (was 1 sync worker)')
