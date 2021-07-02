from django.contrib import admin

# Register your models here.
from .models import (
    Service,
    AuthToken,
    Invitation,
)

class AuthTokenAdmin(admin.ModelAdmin):
     list_display = ('service',
                     'is_token_refreshable',
                     'is_token_accessor',
                     'use_for_ident',
                     'user',
                     'user_ident',
                     'valid',
                     'created_at')

     list_filter = ('valid', )

     def has_add_permission(self, request, obj=None):
          return False

class ServiceAdmin(admin.ModelAdmin):
     list_display = (
         'display_name',
         'short_name',
         'can_use_for_ident')


class InvitationAdmin(admin.ModelAdmin):
     pass


admin.site.register(Service, ServiceAdmin)
admin.site.register(AuthToken, AuthTokenAdmin)
admin.site.register(Invitation)
