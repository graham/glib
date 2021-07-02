from django.contrib.auth.models import User
from django.db import models

from collections import namedtuple

import uuid
import os
# Create your models here.

from . import util

class Service(models.Model):
    # Display name when showing the user.
    display_name = models.CharField(max_length=256)

    # short name for lookups, this determines how this
    # row is found.
    short_name = models.CharField(max_length=256, unique=True)

    # determines which code is run with this row as args.
    service_type = models.CharField(max_length=128)

    # Where the oauth service should redirect on completion.
    redirect_url = models.CharField(max_length=1024, blank=True)

    # If there is an error during the auth process, redirect to this url.
    error_url = models.CharField(max_length=1024, blank=True, default='')

    # what scopes should be requested.
    default_scopes = models.TextField(blank=True)

    client_id = models.CharField(max_length=256, blank=True)
    client_secret = models.CharField(max_length=256, blank=True)
    creds = models.TextField(blank=True)
    can_use_for_ident = models.BooleanField(default=False)

    config_url = models.CharField(max_length=1024, blank=True)

    def __str__(self):
        return self.short_name

    @classmethod
    def get_service(cls, short_name):
        service = util.get_service_config()

        if service:
            for s in service.get('service', []):
                if s.get('short_name') == short_name:
                    myTup = namedtuple('ServiceFromFile', sorted(s))
                    return myTup(**s)
        else:
            return Service.objects.filter(short_name=short_name).first()


class AuthToken(models.Model):
    valid = models.BooleanField()

    service = models.ForeignKey(Service, on_delete=models.CASCADE, null=True, blank=True)
    service_key = models.CharField(max_length=64, default='', null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True)
    state = models.CharField(max_length=256)

    authorized_scopes = models.TextField(blank=True)

    # Email or username of the user.
    user_ident = models.CharField(max_length=256, null=True)

    # Normalized json of user information
    user_info = models.TextField()

    # actual user information from the authorizer.
    data = models.TextField()

    # Time stamps for things.
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Can this 
    use_for_ident = models.BooleanField(default=False)
    is_token_superuser = models.BooleanField(default=False)
    is_token_refreshable = models.BooleanField(default=False)
    is_token_accessor = models.BooleanField(default=False)
    needs_refresh = models.BooleanField(null=True)

    def resync(self):
        from glib.authorizers import auth_lookup
        service = Service.get_service(self.service_key)
        authorizer_cls = auth_lookup.get(service.service_type)
        content = {}
        try:
            content = authorizer_cls.whoami(self.data)
        except Exception as e:
            print("Token failed whoami, marking as invalid", e)
            self.valid = False
            self.save()
            return

        self.valid = True
        user_email = content.get('email')

        if self.authorized_scopes.strip() == '':
            self.authorized_scopes = service.default_scopes

        self.user_ident = user_email
        self.user_info = json.dumps(content)
        self.is_token_refreshable = authorizer_cls.is_refreshable_token(self.data)
        self.save()

    
    @classmethod
    def get_for_service_and_user(cls, service, user):
        return AuthToken.objects.filter(
            service_key=service.short_name,
            user=user,
            valid=True,
            is_token_accessor=True,
        ).order_by('-updated_at').first()

    def ensure_scopes(self, scopes):
        granted_scopes = set([i.strip() for i in self.authorized_scopes.strip().split('\n')])
        desired_scopes = set(scopes)
        return list(desired_scopes - granted_scopes)

    def redirect_to_add_scopes(self, scopes, next_url='/'):
        required_scopes = self.ensure_scopes(scopes)
        if len(required_scopes) > 0:
            service = Service.get_service(self.service_key)        
            return redirect(
                '/auth/start?service={}&add_scopes={}&next={}&consent=1'.format(
                    service.short_name, ','.join(required_scopes), next_url,
                ))
        else:
            return None

    @classmethod
    def cleanup_tokens(cls):
        cls.objects.filter(valid=False).delete()
        


class Invitation(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4)
    invited_by = models.ForeignKey(User,
                                   on_delete=models.CASCADE,
                                   related_name='invited_by')
    accepted_by = models.ForeignKey(User,
                                    on_delete=models.CASCADE,
                                    blank=True,
                                    null=True,
                                    related_name='accepted_by')
    accepted_at = models.DateTimeField(default=None,
                                       blank=True,
                                       null=True)
    
        
