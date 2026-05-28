import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
import django
django.setup()

import requests
import re

session = requests.Session()

# 1. Get login page
resp = session.get('http://localhost:8000/admin/login/?next=/admin/dashboard/')
print(f'1. GET /admin/login/: {resp.status_code}')

# 2. Extract CSRF
match = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', resp.text)
csrf = match.group(1)

# 3. POST login
resp2 = session.post(
    'http://localhost:8000/admin/login/',
    data={'username': 'admin', 'password': 'admin123', 'csrfmiddlewaretoken': csrf, 'next': '/admin/dashboard/'},
    headers={'Referer': 'http://localhost:8000/admin/login/'}
)
print(f'2. POST login: {resp2.status_code}, URL: {resp2.url}')
print(f'   sessionid: {session.cookies.get("sessionid", "NOT SET")[:20]}...')

# 4. Get dashboard HTML and check the template
resp3 = session.get('http://localhost:8000/admin/dashboard/')
print(f'3. GET /admin/dashboard/: {resp3.status_code}')

# Check if "Acceso Restringido" is in the HTML
if 'Acceso Restringido' in resp3.text:
    print('   WARNING: Dashboard shows "Acceso Restringido"')
    # Check if isAdmin is hardcoded to false
    match_isAdmin = re.search(r'isAdmin\s*:\s*false', resp3.text)
    if match_isAdmin:
        print('   FOUND: isAdmin: false hardcoded in template')
else:
    print('   Dashboard loaded correctly')

# Check the init function in the template
match_init = re.search(r'init\(\)\s*\{[^}]+\}', resp3.text)
if match_init:
    print(f'   init function: {match_init.group(0)[:100]}...')

# 5. API metrics with same session
resp4 = session.get('http://localhost:8000/api/v1/admin/metrics/')
print(f'4. GET /api/v1/admin/metrics/: {resp4.status_code}')
if resp4.status_code == 200:
    print(f'   GGR: {resp4.json().get("ggr")}')
else:
    print(f'   Response: {resp4.text[:200]}')