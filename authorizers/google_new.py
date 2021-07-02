import httplib2
import json

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from requests_oauthlib import OAuth2Session

from googleapiclient.discovery import build

class GoogleNewAuthorizer(object):
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
        
    def start(self, service, force_consent=False, add_scopes=None, select_different_account=False):
        scopes = set([i.strip() for i in service.default_scopes.strip().split('\n')])
        if add_scopes is not None:
            for i in add_scopes:
                if i.strip():
                    scopes.add(i)

        consent_arg = 'none'
        if select_different_account is True:
            consent_arg = 'select_account'
        elif force_consent is True:
            consent_arg = 'consent'

        args = dict(
            client_id=service.client_id,
            client_secret=service.client_secret,
            scope=list(scopes),
            redirect_uri=service.redirect_url,

            token_uri="https://oauth2.googleapis.com/token",
            state=self.state_uuid,

        )

        client = OAuth2Session(
            client_id = service.client_id,
            scope=' '.join(scopes),
            redirect_uri=service.redirect_url,
            state=self.state_uuid,
        )

        url, state = client.authorization_url(
            "https://accounts.google.com/o/oauth2/v2/auth",
            state=args.get('state'),
            include_granted_scopes="true",
            access_type="offline" if force_consent is True else 'online',
            prompt=consent_arg,
        )

        return url, state

    def complete(self, service, code, state):
        scopes = set([i.strip() for i in service.default_scopes.strip().split('\n')])

        args = dict(
            client_id=service.client_id,
            client_secret=service.client_secret,
            scope=[i.strip() for i in service.default_scopes.strip().split('\n')],
            redirect_uri=service.redirect_url,
            token_uri="https://oauth2.googleapis.com/token",
            include_granted_scopes="true",
            access_type="offline",
            state=self.state_uuid,
        )

        client = OAuth2Session(
            client_id = service.client_id,
            scope=' '.join(scopes),
            redirect_uri=service.redirect_url,
            state=self.state_uuid,
        )

        token = client.fetch_token(
            "https://oauth2.googleapis.com/token",
            client_secret=service.client_secret,
            code=code,
        )

        return json.dumps(dict(token))

    @classmethod
    def build_client(cls, token):
        obj = json.loads(token)
        return Credentials(
            token=obj.get('access_token'),
            refresh_token=obj.get('refresh_token'),
            token_uri="https://oauth2.googleapis.com/token",
        )

    @classmethod
    def whoami(cls, token):
        creds = cls.build_client(token)
        client = build('people', 'v1', credentials=creds)
        json_content = {}

        response = client.people().get(
            resourceName='people/me',
            personFields='names,photos,emailAddresses',
        ).execute()

        for i in response.get('names', []):
            if i.get('metadata', {}).get('primary') == True:
                json_content['name'] = i.get('displayName')

        for i in response.get('emailAddresses', []):
            if i.get('metadata', {}).get('primary') == True:
                json_content['email'] = i.get('value')

        for i in response.get('photos', []):
            if i.get('metadata', {}).get('primary') == True:
                json_content['picture'] = i.get('url')

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
            for i in result.get(self.items_key):
                self.items_count += 1
                yield i

            if result.get('nextPageToken'):
                self.kwargs['pageToken'] = result.get('nextPageToken')
                result = self.client(**self.kwargs).execute()
            else:
                self.sync_token = result.get('nextSyncToken')
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
