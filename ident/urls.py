from django.urls import path

from . import views
from . import app_views

urlpatterns = [
    path('', views.index, name='index'),
    path('start', views.begin_authorizer_web, name='start'),
    path('complete', views.finish_authorizer_web, name='complete'),

    path('session', views.raw_session, name='raw-session'),
    path('expire', views.expire_session, name='expire'),

    path('authorization_status', views.authorization_status, name='authorization-status'),

    path('login', views.begin_authorizer_web, name='login'),
    path('logout', views.logout_user, name='logout'),
    path('switch_account', views.switch_account, name='switch_account'),
    path('tokens', views.tokens, name='tokens'),

    path('whoami', views.whoami, name='test'),
    path('migrate', views.migrate, name='migrate'),
    path('test', views.test_requirement, name='test'),

    path('accept_invite', views.accept_invite, name='accept_invite'),
    path('apps', app_views.apps, name='apps'),
]
