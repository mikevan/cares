import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app
from models import User, Organization

with app.app_context():
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        print('No user with username "admin" found')
    else:
        print('Admin user id:', admin.id)
        print('Admin organization_id:', admin.organization_id)
        org = Organization.query.get(admin.organization_id)
        if org:
            print('Organization exists. id=%s name=%s' % (org.id, org.name))
        else:
            print('Organization with id %s not found' % admin.organization_id)
        print('Admin active:', admin.active)
