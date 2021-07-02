from django.contrib.auth import decorators 
from django.contrib import admin

login_required = decorators.login_required(login_url='/auth/start')
ident_required = decorators.login_required(login_url='/auth/start?service=google')
user_passes_test = lambda x: decorators.user_passes_test(x, login_url='/auth/start')

def expose_to_staff(cls=None):
    if cls == None:
        class cls(admin.ModelAdmin):
            pass
        
    def justtrue(self, request, *args, **kwargs):
        return True

    cls.has_add_permission = justtrue
    cls.has_change_permission = justtrue
    cls.has_module_permission = justtrue
    cls.has_view_permission = justtrue
    cls.has_delete_permission = justtrue

    return cls

def token_for_service(user, service_name, ident=None):
    from .models import AuthToken, Service

    service = Service.get_service(service_name)

    kwargs = dict(
        user=user,
        valid=True,
        is_token_refreshable=True,
        service_key=service.short_name,
    )

    if ident:
        kwargs['user_ident'] = ident

    token = AuthToken.objects.filter(
        **kwargs
    ).order_by('-updated_at').first()

    return token
    
def client_for_service(user, service_name, ident=None):
    from glib2.authorizers import auth_lookup

    token = token_for_service(user, service_name, ident)
    if token:
        authorizer_cls = auth_lookup.get(service_name)
        return authorizer_cls.build_client(token.data)


def get_contact_info_for(http, emails):
    from glib.authorizers.google import (
        GApiItems
    )
    from googleapiclient.discovery import build

    if len(emails) == 0:
        return {}

    client = build('people', 'v1', http=http)
    data = GApiItems(
        client.people().connections().list,
        resourceName='people/me',
        personFields='names,photos,emailAddresses',
        items_key='connections',
    )

    results = {}

    for d in data.items:
        name = [i.get('displayName', '?') for
                i in d.get('names', [])
                if i['metadata'].get('primary') == True]
        email = [i.get('value', '?') for
                 i in d.get('emailAddresses', [])
                if i['metadata'].get('primary') == True]
        photo = [i.get('url', '?') for
                 i in d.get('photos', [])
                if i['metadata'].get('primary') == True]

        if email and email[0] in emails:
            results[email[0]] = {
                'email': email[0],
                'name': name[0],
                'photo': photo[0],                
            }

    return results
                        
