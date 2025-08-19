from django.urls import path, include

urlpatterns = [
    path('auth/', include('authentication.urls')),
    path('contributions/', include('contributions.urls')),
    path('otps/', include('otps.urls')),
    path('users/', include('users.urls')),
    path('billing/', include('billing.views')),

]
