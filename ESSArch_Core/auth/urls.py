from dj_rest_auth.views import (
    PasswordChangeView,
    PasswordResetConfirmView,
    PasswordResetView,
    UserDetailsView,
)
from django.urls import re_path

from ESSArch_Core.auth.views import LoginView, LogoutView, login_services

urlpatterns = [
    # URLs that do not require a session or valid token
    re_path(r'^password/reset/$', PasswordResetView.as_view(),
            name='rest_password_reset'),
    re_path(r'^password/reset/confirm/$', PasswordResetConfirmView.as_view(),
            name='rest_password_reset_confirm'),
    re_path(r'^login/$', LoginView.as_view(), name='rest_login'),
    re_path(r'^logout/$', LogoutView.as_view(), name='rest_logout'),
    re_path(r'^services/$', login_services, name='services'),
    re_path(r'^user/$', UserDetailsView.as_view(), name='rest_user_details'),
    re_path(r'^password/change/$', PasswordChangeView.as_view(),
            name='rest_password_change'),
]
