from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib.auth.models import User
from django.conf import settings

import enum
import os
import toml


def load_apps(filename):
    if os.path.exists(filename):
        return toml.load(filename)
    return {}

apps_on_load = load_apps('applications.toml')

def apps(request):
    if request.user.is_authenticated:
        data = {}
        if settings.DEBUG is True:
            data = load_apps('applications.toml')
        else:
            data = apps_on_load()

        apps = []

        for app in data.get('app'):
            allow_app = False

            access = app.get("access")

            if access.get('allow') == '*':
                allow_app = True
            elif access.get('allow') == 'allow_list':
                for email in access.get('allow_list', []):
                    if email == request.user.email:
                        allow_app = True

            if allow_app:
                apps.append({
                    'short_name': app.get("short_name"),
                    'scopes': app.get('scopes'),
                })

        
        return JsonResponse({
            'authed': True,            
            'apps': apps,
        })
        
    else:
        return JsonResponse({
            'authed': False,
            'apps': [],
        })

