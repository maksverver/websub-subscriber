import hashlib
import hmac
import secrets

# This isn't really secret; it just needs to be a unique string so that
# different API endpoints don't return valid challenge response by mistake.
SHARED_KEY='websub-internal-validation-key'.encode('utf-8')

def GenerateChallenge():
    return secrets.token_urlsafe()

def GenerateResponse(challenge):
    return hmac.new(SHARED_KEY, challenge.encode('utf-8'), hashlib.sha256).hexdigest()
