from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from django.utils import timezone

User = get_user_model()


# ─────────────────────────────────────────────
# Email OR Mobile Login Backend
# ─────────────────────────────────────────────

class EmailOrMobileBackend(ModelBackend):

    def authenticate(self, request, username=None, password=None, **kwargs):

        if username is None or password is None:
            return None

        user = User.find_by_login(username)

        if not user:
            return None

        if user.is_locked():
            return None

        if user.check_password(password):

            user.clear_login_attempts()

            user.last_login_at = timezone.now()
            user.save(update_fields=["last_login_at"])

            return user

        user.record_failed_login(request=request)

        return None


# ─────────────────────────────────────────────
# API KEY Authentication (for API access)
# ─────────────────────────────────────────────

class APIKeyAuthentication(BaseAuthentication):

    keyword = "Api-Key"

    def authenticate(self, request):

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        parts = auth_header.split()

        if len(parts) != 2:
            raise AuthenticationFailed("Invalid API Key header format")

        if parts[0] != self.keyword:
            return None

        raw_key = parts[1]

        from users.models import APIKey

        key_hash = APIKey.hash_key(raw_key)

        try:
            api_key = APIKey.objects.select_related("user").get(
                key_hash=key_hash,
                is_active=True
            )
        except APIKey.DoesNotExist:
            raise AuthenticationFailed("Invalid API Key")

        api_key.last_used_at = timezone.now()
        api_key.save(update_fields=["last_used_at"])

        return (api_key.user, None)