from django.contrib.auth import authenticate
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import TemplateView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken


class LoginPageView(TemplateView):
    template_name = 'frontend/login.html'


class RegisterPageView(TemplateView):
    template_name = 'frontend/register.html'


class DashboardPageView(TemplateView):
    template_name = 'frontend/dashboard.html'


class EventListView(TemplateView):
    template_name = 'frontend/events/list.html'


class EventDetailView(TemplateView):
    template_name = 'frontend/events/detail.html'


class BetListView(TemplateView):
    template_name = 'frontend/bets/list.html'


class WalletBalanceView(TemplateView):
    template_name = 'frontend/wallet/balance.html'


class WalletDepositView(TemplateView):
    template_name = 'frontend/wallet/deposit.html'


class ResponsibleLimitsView(TemplateView):
    template_name = 'frontend/responsible/limits.html'


class ResponsibleSelfExcludeView(TemplateView):
    template_name = 'frontend/responsible/self_exclude.html'


@method_decorator(csrf_exempt, name='dispatch')
class LoginAPIView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return Response(
                {'error': 'Usuario y contraseña son requeridos.'},
                status=400,
            )

        user = authenticate(username=username, password=password)
        if user is None:
            return Response(
                {'error': 'Credenciales inválidas.'},
                status=400,
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
            },
        })
