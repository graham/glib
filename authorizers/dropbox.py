import json
import dropbox

CSRF_SESSION_KEY = "csrf"

class DropboxAuthorizer(object):
    def __init__(self, state_uuid):
        self.state_uuid = state_uuid

    @classmethod
    def is_refreshable_token(cls, token):
        return True

    @classmethod
    def garden_tokens(cls, user_tokens):
        for t in user_tokens[1:]:
            t.valid = False
            t.save()

        return False

    def start(self, service, *args, **kwargs):
        flow = dropbox.DropboxOAuth2Flow(
            consumer_key=service.client_id,
            consumer_secret=service.client_secret,
            redirect_uri=service.redirect_url,
            session={},
            csrf_token_session_key=CSRF_SESSION_KEY,
        )

        result = flow.start(self.state_uuid)

        return result, flow.session[CSRF_SESSION_KEY] + "|" + self.state_uuid

    def complete(self, service, code, state):
        csrf_token, uuid = state.split("|")
        
        c = {'code':code, 'state': state}
        flow = dropbox.DropboxOAuth2Flow(
            consumer_key=service.client_id,
            consumer_secret=service.client_secret,
            redirect_uri=service.redirect_url,
            session={CSRF_SESSION_KEY: csrf_token},
            csrf_token_session_key=CSRF_SESSION_KEY,
        )

        result = flow.finish(c)
        return result.access_token

    @classmethod
    def build_client(cls, token):
        return dropbox.Dropbox(token)

    @classmethod
    def whoami(cls, token):
        account_info = cls.build_client(token).users_get_current_account()

        return {
            'email': account_info.email,
            'email_verified': account_info.email_verified,
            'picture': account_info.profile_photo_url,
        }

    
        
        
