from django.urls import path

from authentication.views import AuthenticationAPIHandler

handler = AuthenticationAPIHandler()

urlpatterns = [
    path('login/', handler.login, name='auth-login'),
    path('logout/', handler.logout, name='auth-logout'),
]
