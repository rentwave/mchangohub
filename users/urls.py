from django.urls import path
from users.views import UserAPIHandler

handler = UserAPIHandler()

urlpatterns = [
    path('check/', handler.check_user, name='user-check'),
    path('create/', handler.create_user, name='user-create'),
    path('delete/', handler.delete_user, name='user-delete'),
    path('update/', handler.update_user, name='user-update'),
    path('change-password/', handler.change_password, name='user-change-password'),
    path('reset-password/', handler.reset_password, name='user-reset-password'),
    path('forgot-password/', handler.forgot_password, name='user-forgot-password'),
    path('get/', handler.get_user, name='user-get'),
    path('filter/', handler.filter_users, name='user-filter'),
    path('devices/create/', handler.create_device, name='device-create'),
    path('devices/deactivate/', handler.deactivate_device, name='device-deactivate'),
]
