"""
One-time helper: set the REGALIA (Knights of Columbus) stylesheet + logo
on any organization that doesn't already have a custom css_file set.

Run this locally (where your Postgres/DATABASE_URL is actually reachable):

    python scripts/set_kofc_branding.py

It's safe to re-run: organizations that already have a css_file set (e.g. a
future client with their own branding) are left untouched and reported.
"""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from models import db, Organization

with app.app_context():
    orgs = Organization.query.all()
    if not orgs:
        print('No organizations found — nothing to update.')
        sys.exit(0)

    changed = 0
    for org in orgs:
        if org.css_file:
            print(f'Skipping org {org.id} ("{org.name}") — already has css_file="{org.css_file}"')
            continue
        org.css_file = 'kofc.css'
        changed += 1
        print(f'Set org {org.id} ("{org.name}") -> css_file="kofc.css"')

    if changed:
        db.session.commit()
        print(f'\nDone — updated {changed} organization(s).')
    else:
        print('\nNo changes needed — every organization already has a css_file set.')
