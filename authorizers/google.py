import httplib2
import json

from oauth2client.client import (
    OAuth2WebServerFlow,
    Credentials,
    FlowExchangeError,
    HttpAccessTokenRefreshError
)

from googleapiclient.discovery import build

class GoogleAuthorizer(object):
    def __init__(self, state_uuid):
        self.state_uuid = state_uuid

    @classmethod
    def is_refreshable_token(cls, token):
        token = json.loads(token)
        if token.get('refresh_token', None) is not None:
            return True
        return False

    @classmethod
    def garden_tokens(cls, user_tokens):
        found_refresh = False

        for t in user_tokens:
            data = json.loads(t.data)
            if data.get('refresh_token'):
                found_refresh = True
            else:
                t.valid = False
                t.save()

        return found_refresh
        
    def start(self, service, force_consent=False, add_scopes=None, select_different_account=False, account_hint='', full_scope=False):
        scopes = set()

        if full_scope is True:
            scopes = set([i.strip() for i in service.default_scopes.strip().split('\n')])

        if add_scopes is not None and len(add_scopes) > 0:
            for i in add_scopes:
                if i.strip():
                    scopes.add(i)

            scopes = list(scopes)

        consent_arg = None
        if select_different_account is True:
            consent_arg = 'select_account'
        elif force_consent is True:
            consent_arg = 'consent'

        args=dict(
            client_id=service.client_id,
            client_secret=service.client_secret,
            scope=list(scopes) or 'https://www.googleapis.com/auth/userinfo.email',
            redirect_uri=service.redirect_url,
            token_uri="https://oauth2.googleapis.com/token", 
            state=self.state_uuid,
        )

        if account_hint:
            args['login_hint'] = account_hint

        if consent_arg:
            args['access_type'] = "offline" if force_consent is True else 'online'
            args['include_granted_scopes'] = "true"
            args['prompt'] = consent_arg
        
        flow = OAuth2WebServerFlow(
            **args,
        )

        return flow.step1_get_authorize_url(), self.state_uuid

    def complete(self, service, code, state):
        code = code.replace('%2F', '/')
        flow = OAuth2WebServerFlow(
            client_id=service.client_id,
            client_secret=service.client_secret,
            scope=[i.strip() for i in service.default_scopes.strip().split('\n')],
            redirect_uri=service.redirect_url,
            token_uri="https://oauth2.googleapis.com/token",
            include_granted_scopes="true",
            access_type="offline",
            state=self.state_uuid,
        )
        try:
            return flow.step2_exchange(code).to_json()
        except FlowExchangeError as fee:
            print(fee)
            return None

    @classmethod
    def build_client(cls, token):
        credentials = Credentials.new_from_json(token)
        http = httplib2.Http()
        http = credentials.authorize(http)
        return http

    @classmethod
    def whoami(cls, token):
        client = cls.build_client(token)
        r, content = client.request('https://openidconnect.googleapis.com/v1/userinfo')
        json_content = json.loads(content)

        return {
            'email': json_content.get('email'),
            'picture': json_content.get('picture'),
            'email_verified': json_content.get('email_verified'),
        }

######################################################

class GApiItems(object):
    def __init__(self, client, items_key='items', **kwargs):
        self.client = client
        self.items_key = items_key
        self.kwargs = kwargs
        self.sync_token = ''
        self.pages = 0
        self.is_complete = False
        self.items_count = 0

        self.error = False
        self.error_detail = ''

    @property
    def items(self):
        return self._items()

    def get_pages(self, page_count=1):
        return self._items(page_count)

    def _items(self, page_count=None):
        running = True

        if self.is_complete is True:
            raise Exception("This iterator is complete, please recreate")

        try:
            result = self.client(**self.kwargs).execute()
        except HttpAccessTokenRefreshError as hatre:
            self.error = True
            self.error_detail = 'invalid_token'
            return []

        if 'syncToken' in self.kwargs:
            del self.kwargs['syncToken']

        while True:
            self.pages += 1

            if isinstance(self.items_key, list):
                self.items_count += 1
                d = {}
                for k in self.items_key:
                    d[k] = result.get(k)
                yield d
            else:
                for i in result.get(self.items_key):
                    self.items_count += 1
                    yield i

            if result.get('nextPageToken'):
                self.kwargs['pageToken'] = result.get('nextPageToken')
                result = self.client(**self.kwargs).execute()
            else:
                self.sync_token = result.get('nextSyncToken')
                return

            if page_count is not None:
                if page_count <= self.pages:
                    return

    def next(self):
        newKwargs = dict(self.kwargs)
        newKwargs['syncToken'] = self.sync_token
        if 'pageToken' in newKwargs:
            del newKwargs['pageToken']            

        return GApiItems(
            client=self.client,
            items_key=self.items_key,
            **self.kwargs)


