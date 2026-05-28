# -*- coding: utf-8 -*-
from django.contrib.auth import authenticate, login
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse


@csrf_exempt
def admin_login_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    import json
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=400)

    username = data.get('username')
    password = data.get('password')

    if not username or not password:
        return JsonResponse({'error': 'Usuario y contraseña son requeridos'}, status=400)

    user = authenticate(request, username=username, password=password)

    if user is not None and (user.is_staff or user.is_superuser):
        login(request, user)
        return JsonResponse({
            'success': True,
            'username': user.username,
            'is_staff': user.is_staff,
            'redirect_url': '/admin/dashboard/'
        }, status=200)
    else:
        return JsonResponse({
            'error': 'Credenciales inválidas o no tiene permisos de administrador'
        }, status=401)