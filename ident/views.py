from django.shortcuts import render, redirect
from django.http import HttpResponse, JsonResponse, Http404
from django.contrib.auth.models import User
from django.contrib.auth import login, logout

import uuid
import json
import os
import datetime

from oauth2client.client import (
    HttpAccessTokenRefreshError,
)

from .models import Service, AuthToken, Invitation
from .helpers import login_required, token_for_service
from glib2.helpers import SERVER_CONST_REVISION
from glib2.authorizers import auth_lookup

import enum
from . import util


class AuthError(enum.Enum):
    NON_IDENT_TOKEN_WHEN_NOT_AUTHENTICATED = 1
    SERVICE_NOT_FOUND = 2
    INVALID_TOKEN = 3
    NO_USER_MODEL = 4
    HANDSHAKE_FAILED = 5
    WHOAMI_FAILED = 6
    WHOAMI_FAILED_TO_IDENT = 7
    USER_NOT_ALLOWED_TO_AUTHENTICATE = 8
    EMAIL_NOT_VERIFIED = 9
    SERVICE_ERROR = 10
    TOKEN_MISSING = 11


def handle_error(request, service, error_enum, **kwargs):
    if error_enum == AuthError.NON_IDENT_TOKEN_WHEN_NOT_AUTHENTICATED:
        return HttpResponse(
            "You must be authenticated in order to add a non-identity token")
    elif error_enum == AuthError.SERVICE_NOT_FOUND:
        return HttpResponse("That service doesn't exist.")
    elif error_enum == AuthError.INVALID_TOKEN:
        return HttpResponse("That token is not valid")
    elif error_enum == AuthError.NO_USER_MODEL:
        return HttpResponse("Your token was not associated with a user.")        
    elif error_enum == AuthError.WHOAMI_FAILED:
        return HttpResponse("Your request was invalid, please try again.")
    elif error_enum == AuthError.WHOAMI_FAILED_TO_IDENT:
        return HttpResponse("This service doesn't have access to userinfo, please request this scope")
    elif error_enum == AuthError.USER_NOT_ALLOWED_TO_AUTHENTICATE:
        return HttpResponse("{} does not have access to this application.".format(kwargs.get('user_email')))
    elif error_enum == AuthError.EMAIL_NOT_VERIFIED:
        return HttpResponse("The account {} for {} is not verified and cannot be used.".format(
            service.display_name, user_email))
    elif error_enum == AuthError.SERVICE_ERROR:
        return HttpResponse("This service returned an error: {} {}.".format(
            request.GET.get('error'), request.GET.get('error_subtype')))
    elif error_enum == AuthError.TOKEN_MISSING:
        return HttpResponse("For some reason your token is missing.".format())
    else:
        return HttpResponse("This error is not handled correctly.")


# Here is where you should determine if a user is eligible to use
# your application
def can_user_use_application(email, invitation=None):
    # first check to see if the user already has a user object.
    can_use = False

    if User.objects.filter(email=email, is_active=True).first():
        return True

    if invitation is not None:
        can_use = can_use or True

    service = util.get_service_config().get('user_info', None)

    if service:
        allowed_users = service.get('allowed_users', [])
        if allowed_users:
            ALLOWED_EMAILS = set([i.strip().lower() for i in allowed_users])
            can_use = can_use or (email.strip().lower() in ALLOWED_EMAILS)

        allowed_domains = service.get('allowed_domains', [])
        if allowed_domains:
            ALLOWED_DOMAINS = set([i.strip().lower() for i in allowed_domains])
            domain = email.split('@')[-1]
            can_use = can_use or (domain.strip().lower() in ALLOWED_DOMAINS)
    else:
        if os.path.exists('allowed_emails.txt'):
            ALLOWED_EMAILS = set([
                i.strip().lower() for i in open("allowed_emails.txt").read().strip().split("\n")
                if len(i.strip()) > 0 and i[0] != '#'
            ])
            can_use = can_use or (email.strip().lower() in ALLOWED_EMAILS)

        if os.path.exists('allowed_domains.txt'):
            ALLOWED_DOMAINS = set([
                i.strip().lower() for i in open("allowed_domains.txt").read().strip().split("\n")
                if len(i.strip()) > 0 and i[0] != '#'
            ])
            domain = email.split('@')[-1]
            can_use = can_use or (domain.strip().lower() in ALLOWED_DOMAINS)

    return can_use


# Create your views here.
def index(request):
    return HttpResponse("Hello World")


def logout_user(request):
    logout(request)
    return HttpResponse("You are logged out. <script>localStorage.clear(); sessionStorage.clear();</script>")

def switch_account(request):
    next_url = request.GET.get('next') or request.META.get('HTTP_REFERER') or '/'
    service_name = request.GET.get('service') or 'google'

    service = Service.get_service(service_name)

    if not service:
        return handle_error(request, None, AuthError.SERVICE_NOT_FOUND)

    uid = uuid.uuid4().hex
    
    token = AuthToken(service_key=service.short_name,
                      authorized_scopes='',
                      valid=False,
                      use_for_ident=False,
                      data='')

    if service.can_use_for_ident is True:
        token.user = None
        token.use_for_ident = True
    else:
        if request.user.is_authenticated:
            token.user = request.user
        else:
            return handle_error(request,
                                service,
                                AuthError.NON_IDENT_TOKEN_WHEN_NOT_AUTHENTICATED)

    authorizer_cls = auth_lookup.get(service.service_type)
    authorizer = authorizer_cls(uid)

    auth_url, state = authorizer.start(service=service,
                                       force_consent=False,
                                       add_scopes=None,
                                       select_different_account=True)
                                       
    token.state = state
    token.save()

    response = redirect(auth_url)
    response.set_cookie("next", next_url)
    response.set_cookie("is_switch", '1')
    return response


@login_required
def test_requirement(request):
    return HttpResponse("You made it.")

def expire_session(request):
    request.session.set_expiry(5)
    return HttpResponse("Ok, expired")

def raw_session(request):
    session_expiry_date = request.session.get_expiry_date()
    return HttpResponse("expires: {}".format(session_expiry_date))

def authorization_status(request):
    service_name = request.GET.get('service') or 'google'
    service = Service.get_service(service_name)

    d = {
        'authed': False,
        'has_refresh': False,
        'has_accessor': False,
        'has_refresh_and_accessor': False,
    }

    if request.user.is_authenticated:
        d['authed'] = True

        d['has_refresh'] = AuthToken.objects.filter(
            valid=True,
            user=request.user,
            service_key=service.short_name,
            is_token_refreshable=True,
        ).first() != None
        
        d['has_accessor'] = AuthToken.objects.filter(
            valid=True,
            user=request.user,
            service_key=service.short_name,
            is_token_accessor=True,
        ).first() != None

        d['has_refresh_and_accessor'] = AuthToken.objects.filter(
            valid=True,
            user=request.user,
            service_key=service.short_name,
            is_token_refreshable=True,
            is_token_accessor=True,
        ).first() != None

    return JsonResponse(d)


def whoami(request):
    if request.user.is_authenticated:
        return JsonResponse({
            'authed': True,
            'email': request.user.email,
            'whoami':request.user.email,
            'is_guest': False,
            'server_version': SERVER_CONST_REVISION,
            'marked_for_update': request.session.get('marked_for_update', False),
        })
    else:
        return JsonResponse({
            'authed': False,
            'email': None,
            'whoami':'guest',
            'is_guest': True,
            'server_version': SERVER_CONST_REVISION,
            'marked_for_update': request.session.get('marked_for_update', False),
        })

def tokens(request):
    if request.GET.get('cleanup') == '1':
        pass

    if request.user.is_authenticated:
        tokens = AuthToken.objects.filter(
            user=request.user,
            valid=True,
        ).order_by('-updated_at')

        ts = [
            {
                'service': t.service.short_name,
                'ident': t.user_ident,
                'refreshable': t.is_token_refreshable,
            }
            
        for t in tokens]

        return JsonResponse({
            'tokens': ts,
        })
    else:
        return JsonResponse({})
    

    
def migrate(request):
    from glib2.helpers import fire_event
    fire_event('migrate', request, url='migrate')
    next_url = request.GET.get('next') or '/'
    return redirect(next_url)


def begin_authorizer_web(request, force_service=None, force_ident=None):
    next_url = request.GET.get('next') or '/'
    service_name = force_service or request.GET.get('service') or 'google'
    use_for_identity = force_ident or bool(int(request.GET.get('ident') or '1'))
    force_consent = bool(int(request.GET.get('consent') or '0'))
    select_account = bool(int(request.GET.get('select_account') or '0'))
    foreign_client = bool(int(request.GET.get('foreign') or '0'))
    accept_invite_key = request.GET.get('invite_key', '')
    account_hint = request.GET.get('hint', '')

    if request.user.is_authenticated:
        if account_hint == '':
            account_hint = request.user.email

    add_scopes = (request.GET.get('add_scopes') or '').split(',')
    if add_scopes == ['']:
        add_scopes = []

    service = Service.get_service(service_name)

    if not service:
        return handle_error(request, None, AuthError.SERVICE_NOT_FOUND)

    uid = uuid.uuid4().hex
    
    token = AuthToken(service_key=service.short_name,
                      authorized_scopes='',
                      valid=False,
                      use_for_ident=False,
                      data='')

    if service.can_use_for_ident is True and use_for_identity == True:
        token.user = None
        token.use_for_ident = True
    else:
        if request.user.is_authenticated:
            token.user = request.user
        else:
            return handle_error(request,
                                service,
                                AuthError.NON_IDENT_TOKEN_WHEN_NOT_AUTHENTICATED)

    authorizer_cls = auth_lookup.get(service.service_type)
    authorizer = authorizer_cls(uid)

    auth_url, state = authorizer.start(service,
                                       force_consent=force_consent,
                                       add_scopes=add_scopes,
                                       select_different_account=select_account,
                                       account_hint=account_hint,
                                       full_scope=force_consent)
    token.state = state
    token.save()

    if foreign_client:
        response = HttpResponse(json.dumps({'link':auth_url, 'service':service_name}))
        response.set_cookie('foreign', '1')
        return response
    else:
        response = redirect(auth_url)
        response.set_cookie("next", next_url)
        if accept_invite_key:
            response.set_cookie("invite_key", accept_invite_key)
        return response


def finish_authorizer_web(request):
    state = request.GET.get('state')
    code = request.GET.get('code')
    scope = request.GET.get('scope', '').strip()
    token = AuthToken.objects.filter(state=state).first()

    if not token:
        return redirect(
            '/auth/start?consent=1&next={}&reason=notoken'.format(
                request.COOKIES.get('next') or '/'))

    service = Service.get_service(token.service_key)
    authorizer_cls = auth_lookup.get(service.service_type)
    authorizer = authorizer_cls(state)

    if (request.GET.get('error') == 'interaction_required' and
        request.GET.get('error_subtype') == 'access_denied'):
        print("ACCESS DENIED, LETS RETRY")
        auth_url, state = authorizer.start(service,
                                           force_consent=True,
                                           add_scopes=[],
                                           select_different_account=False,
                                           account_hint=None)
        token.state = state
        token.save()
        response = redirect(auth_url)
        response.set_cookie("next", request.COOKIES.get('next') or '/')
        return response

    if request.GET.get('error', None) != None:
        return handle_error(request, None, AuthError.SERVICE_ERROR)

    if token.use_for_ident is False and token.user is None:
        return handle_error(request, Service.get_service(token.service_key), AuthError.NO_USER_MODEL)

    try:
        complete = authorizer.complete(service, code, state)
    except:
        import traceback
        traceback.print_exc()

    if complete is None:
        token.valid = False
        token.save()
        return handle_error(request, service, AuthError.INVALID_TOKEN)

    token.data = complete
    token.is_token_refreshable = authorizer.is_refreshable_token(complete)

    if scope:
        clean_defaults = [i.strip() for i in service.default_scopes.split('\n') if i.strip()]
        clean_scopes = sorted([i.strip() for i in scope.split() if i.strip()])
        token.authorized_scopes = '\n'.join(clean_scopes)
        if all([i in clean_scopes for i in clean_defaults]):
            token.is_token_accessor = True
        

    try:
        content = authorizer.whoami(token.data)
    except HttpAccessTokenRefreshError as hatre:
        token.delete()
        return handle_error(request, service, AuthError.WHOAMI_FAILED)

    user_email = content.get('email')
    is_email_verified = content.get('email_verified', False)

    # Refresh tokens are used by some services, but are not apart of
    # the response if the user is only authenticating (no consent page).
    # if this is null, we should determine if we need to go through
    # the full flow.
    refresh_token = content.get('refresh_token', None)

    invitation = None
    if request.COOKIES.get('invite_key'):
        invitation = Invitation.objects.filter(
            uuid=request.COOKIES.get('invite_key'),
            accepted_at=None).first()

    if (service.can_use_for_ident == True and
        token.use_for_ident == True and
        is_email_verified == False):
        return handle_error(request, service, AuthError.EMAIL_NOT_VERIFIED)

    token.user_ident = user_email
    token.user_info = json.dumps(content)
    token.save()

    if user_email is None:
        return handle_error(request, service, AuthError.WHOAMI_FAILED_TO_IDENT)
    elif can_user_use_application(user_email, invitation) == False:
        return handle_error(request,
                            service,
                            AuthError.USER_NOT_ALLOWED_TO_AUTHENTICATE,
                            user_email=user_email)

    token.needs_update = False
    token.valid = True

    if service.can_use_for_ident and token.use_for_ident == True:
        user = User.objects.filter(email=user_email).first()

        if not user:
            user = User(email=user_email,
                        username=user_email)
            user.set_unusable_password()
            user.save()

        if invitation is not None:
            invitation.accepted_by = user
            invitation.accepted_at = datetime.datetime.now()
            invitation.save()

        token.user = user
        login(request, token.user)

    token.save()
    
    user_tokens = AuthToken.objects.filter(
        valid=True,
        service_key=service.short_name,
        user=token.user,
    ).order_by('-updated_at')

    current_token_with_refresh = authorizer_cls.is_refreshable_token(token.data)
    garden_result = authorizer_cls.garden_tokens(user_tokens)

    if (current_token_with_refresh or garden_result or not token.is_token_accessor) is False:
        if request.COOKIES.get('is_switch') == '1':
            auth_url, state = authorizer.start(service,
                                               force_consent=True,
                                               add_scopes=[],
                                               select_different_account=False,
                                               account_hint=token.user.email,
                                               full_scope=True)
            token.state = state
            token.save()
            if service.error_url.strip():
                args = {
                    'is_switch': 1,
                }

                full_url = ''
                
                if '?' in service.error_url:
                    full_url = service.error_url + '&' + '&'.join(
                        ['{}={}'.format(k, v) for k, v in args.items()])
                else:
                    full_url = service.error_url + '?' + '&'.join(
                        ['{}={}'.format(k, v) for k, v in args.items()])

                redirect(full_url)
            else:
                return HttpResponse("Switching to a new account we haven't seen before, " +
                                    "so we'll need you to go through the full auth flow," +
                                    "<a href='{}'>Click Here</a>".format(auth_url))
        else:
            auth_url, state = authorizer.start(service,
                                               force_consent=True,
                                               add_scopes=[],
                                               select_different_account=False,
                                               account_hint=token.user.email,
                                               full_scope=True)
            token.state = state
            token.save()
            if service.error_url.strip():
                clean_defaults = [i.strip() for i in service.default_scopes.split('\n')]
                clean_scopes = sorted([i.strip() for i in scope.split()])

                missing_scopes = [i for i in clean_defaults if i not in clean_scopes]

                args = {
                    'token_expired': 1,
                    'missing_scopes': ','.join(missing_scopes),
                }

                full_url = ''
                
                if '?' in service.error_url:
                    full_url = service.error_url + '&' + '&'.join(
                        ['{}={}'.format(k, v) for k, v in args.items()])
                else:
                    full_url = service.error_url + '?' + '&'.join(
                        ['{}={}'.format(k, v) for k, v in args.items()])

                print("WE NEED MORE ACCESS")
                redirect(full_url)
            else:
                return HttpResponse(
                    "It looks like our access token has expired " +
                    "or we need some additional permissions " +
                    "please re-authorize to grant access " +
                    "<a href='{}'>Click Here</a>".format(auth_url))


    # After all that, lets make sure we clean up the tokens we have.
    target_url = request.COOKIES.get('next') or '/'
    response = redirect(target_url)

    response.delete_cookie('next')
    response.delete_cookie('is_switch')

    if target_url.startswith('/admin/') and token.user.is_staff is False:
        # you should remove this at some point.
        service = util.get_service_config().get('user_info', None)

        if service:
            if user_email.lower() in service.get('admins'):
                user.is_staff = True
                user.is_superuser = True
                user.save()
            else:
                raise Http404()
        else:
            if os.path.exists('auto_admins.txt'):
                AUTO_ADMIN_EMAILS = set([
                    i.strip().lower() for i in open("auto_admins.txt").read().strip().split("\n")
                    if len(i.strip()) > 0 and i[0] != '#'
                ])
                is_admin = (user_email.strip().lower() in AUTO_ADMIN_EMAILS)

                if is_admin:
                    user.is_staff = True
                    user.is_superuser = True
                    user.save()
                else:
                    raise Http404()
            else:
                raise Http404()

    return response

def add_scopes_view(request):
    service_name = request.GET.get('service').strip()
    scopes = request.GET.get('scopes')
    next_url = request.GET.get('next') or '/'

    token = token_for_service(request.user, service_name)

    current_scopes = set([i.strip() for i in token.authorized_scopes.split('\n')])
    adding_scopes = set([i.strip() for i in scopes.split(',')])

    missing_scopes = adding_scopes - current_scopes

    if missing_scopes:
        return redirect(
            '/auth/start?service={}&add_scopes={}&next={}&consent=1&reason=missing_scopes'.format(
                service_name, ','.join(missing_scopes), next_url,
            ))
    else:
        return redirect(next_url)
    

def accept_invite(request):
    code = request.GET.get('code', '').strip()

    invite = Invitation.objects.filter(uuid=code, accepted_at=None).first()

    if invite is None:
        return HttpResponse("That code is not valid.")
    else:
        response = redirect('/auth/start?invite_key={}'.format(invite.uuid))
        response.set_cookie("next", '/?invite_accepted=1')
        return response
        
