import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.dev')
import django
django.setup()

from django.urls import reverse

try:
    url = reverse('admin-dashboard')
    print(f'reverse(admin-dashboard) = {url}')
except Exception as e:
    print(f'Error reversing admin-dashboard: {e}')

try:
    url = reverse('admin-login')
    print(f'reverse(admin-login) = {url}')
except Exception as e:
    print(f'Error reversing admin-login: {e}')