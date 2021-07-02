from .google import GoogleAuthorizer
from .google_new import GoogleNewAuthorizer
#from .dropbox import DropboxAuthorizer
#from .github import GithubAuthorizer
#from .reddit import RedditAuthorizer

auth_lookup = {
    'google': GoogleAuthorizer,
#   'google': GoogleNewAuthorizer,
#   'dropbox': DropboxAuthorizer,
#   'github': GithubAuthorizer,
#   'reddit': RedditAuthorizer,
}
