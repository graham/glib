import httplib2
import json
from github import Github

from oauth2client.client import (
    OAuth2WebServerFlow,
    Credentials,
    FlowExchangeError,
    HttpAccessTokenRefreshError
)


class GithubAuthorizer(object):
    def __init__(self, state_uuid):
        self.state_uuid = state_uuid

    @classmethod
    def is_refreshable_token(cls, token):
        return True
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

        return not found_refresh        
        
    def start(self, service, force_consent=False, add_scopes=None, select_different_account=False):
        scopes = set([i.strip() for i in service.default_scopes.strip().split('\n')])
        if add_scopes is not None:
            for i in add_scopes:
                if i.strip():
                    scopes.add(i)

        consent_arg = 'none'
        if force_consent is True:
            consent_arg = 'consent'
        elif select_different_account is True:
            consent_arg = 'select_account'

        flow = OAuth2WebServerFlow(
            client_id=service.client_id,
            client_secret=service.client_secret,
            scope=list(scopes),
            auth_uri="https://github.com/login/oauth/authorize",
            redirect_uri=service.redirect_url,
            token_uri="https://github.com/login/oauth/access_token",
            include_granted_scopes="true",
            state=self.state_uuid,
            access_type="offline" if force_consent is True else 'online',
            prompt=consent_arg,
        )
        return flow.step1_get_authorize_url(), self.state_uuid

    def complete(self, service, code, state):
        flow = OAuth2WebServerFlow(
            client_id=service.client_id,
            client_secret=service.client_secret,
            auth_uri="https://github.com/login/oauth/authorize",            
            scope=[i.strip() for i in service.default_scopes.strip().split('\n')],
            redirect_uri=service.redirect_url,
            token_uri="https://github.com/login/oauth/access_token",
            include_granted_scopes="true",
            access_type="offline",
            state=self.state_uuid,
        )
        try:
            result = flow.step2_exchange(code).to_json()
            return result
        except FlowExchangeError as fee:
            return None

    @classmethod
    def build_client(cls, token):
        data = json.loads(token)
        at = data.get('access_token')
        return Github(at)

    @classmethod
    def whoami(cls, token):
        client = cls.build_client(token)
        user = client.get_user()

        return {
            'email': user.email,
            'picture': user.avatar_url,
            'email_verified': True,
            'login': user.login,
        }
