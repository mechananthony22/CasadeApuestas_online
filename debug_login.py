import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
import django
django.setup()

import requests

session = requests.Session()

# 1. Get login page
resp = session.get('http://localhost:8000/admin/login/')
print(f'1. GET /admin/login/: {resp.status_code}')

# 2. Extract CSRF
import re
match = re.search(r'csrfmiddlewaretoken.*?value="([^"]+)"', resp.text)
csrf_token = match.group(1) if match else session.cookies.get('csrftoken')
print(f'   CSRF: {csrf_token}')

# 3. POST login
resp2 = session.post(
    'http://localhost:8000/admin/login/',
    data={
        'username': 'admin',
        'password': 'admin123',
        'csrfmiddlewaretoken': csrf_token,
        'next': '/admin/dashboard/'
    },
    headers={'Referer': 'http://localhost:8000/admin/login/'}
)
print(f'2. POST /admin/login/: {resp2.status_code} - URL: {resp2.url}')
print(f'   Session cookies: {dict(session.cookies)}')

# 4. Access dashboard
resp3 = session.get('http://localhost:8000/admin/dashboard/')
print(f'3. GET /admin/dashboard/: {resp3.status_code}')

# 5. Call API metrics (same session)
resp4 = session.get(
    'http://localhost:8000/api/v1/admin/metrics/',
    headers={'Referer': 'http://localhost:8000/admin/dashboard/'}
)
print(f'4. GET /api/v1/admin/metrics/: {resp4.status_code}')
if resp4.status_code != 200:
    print(f'   Response: {resp4.text[:500]}')
else:
    print(f'   Response: {resp4.json().get("ggr", "N/A")}')