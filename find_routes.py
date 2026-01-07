# find_routes.py
from app import app

print("=" * 60)
print("YOUR FLASK ROUTES")
print("=" * 60)
print()

# Group routes by category
dashboard_routes = []
member_routes = []
project_routes = []
transaction_routes = []
report_routes = []
other_routes = []

for rule in app.url_map.iter_rules():
    if rule.endpoint == 'static':
        continue
    
    route_info = f"Function: {rule.endpoint:25} URL: {rule.rule}"
    
    # Categorize routes
    if 'member' in rule.endpoint.lower():
        member_routes.append(route_info)
    elif 'project' in rule.endpoint.lower():
        project_routes.append(route_info)
    elif 'transaction' in rule.endpoint.lower():
        transaction_routes.append(route_info)
    elif 'report' in rule.endpoint.lower():
        report_routes.append(route_info)
    elif rule.endpoint in ['index', 'home', 'dashboard']:
        dashboard_routes.append(route_info)
    else:
        other_routes.append(route_info)

# Print organized output
if dashboard_routes:
    print("DASHBOARD:")
    for route in dashboard_routes:
        print(f"  {route}")
    print()

if member_routes:
    print("MEMBERS:")
    for route in member_routes:
        print(f"  {route}")
    print()

if project_routes:
    print("PROJECTS:")
    for route in project_routes:
        print(f"  {route}")
    print()

if transaction_routes:
    print("TRANSACTIONS:")
    for route in transaction_routes:
        print(f"  {route}")
    print()

if report_routes:
    print("REPORTS:")
    for route in report_routes:
        print(f"  {route}")
    print()

if other_routes:
    print("OTHER:")
    for route in other_routes:
        print(f"  {route}")
    print()

print("=" * 60)
print()
print("To use in templates: {{ url_for('function_name') }}")
print()
print("Example: {{ url_for('members') }} for the 'members' function")
print("=" * 60)