from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.utils import timezone

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


User = get_user_model()


# ─────────────────────────────────────────────
# Email OR Mobile Login Backend
# ─────────────────────────────────────────────
class EmailOrMobileBackend(ModelBackend):

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        **kwargs
    ):
        """
        Authenticate using either:
        - email address
        - mobile number

        Supports both:
            authenticate(username="...")
        and:
            authenticate(email="...")
            authenticate(mobile_number="...")
        """

        if password is None:
            return None

        # Accept username, email, or mobile_number
        login_value = (
            username
            or kwargs.get("email")
            or kwargs.get("mobile_number")
        )

        if not login_value:
            return None

        # Find the user using the project's existing helper
        user = User.find_by_login(login_value)

        if not user:
            return None

        # Check account lock status
        if user.is_locked():
            return None

        # Check password
        if user.check_password(password):
            # Successful login
            user.clear_login_attempts()

            user.last_login_at = timezone.now()

            user.save(
                update_fields=["last_login_at"]
            )

            return user

        # Failed login
        user.record_failed_login(request=request)

        return None


# ─────────────────────────────────────────────
# API KEY Authentication
# ─────────────────────────────────────────────
class APIKeyAuthentication(BaseAuthentication):
    """
    Authenticate API requests using:

        Authorization: Api-Key <API_KEY>
    """

    keyword = "Api-Key"

    def authenticate(self, request):

        auth_header = request.headers.get("Authorization")

        if not auth_header:
            return None

        parts = auth_header.split()

        if len(parts) != 2:
            raise AuthenticationFailed(
                "Invalid API Key header format"
            )

        if parts[0] != self.keyword:
            return None

        raw_key = parts[1]

        from users.models import APIKey

        key_hash = APIKey.hash_key(raw_key)

        try:
            api_key = (
                APIKey.objects
                .select_related("user")
                .get(
                    key_hash=key_hash,
                    is_active=True
                )
            )

        except APIKey.DoesNotExist:
            raise AuthenticationFailed(
                "Invalid API Key"
            )

        # Update last-used timestamp
        api_key.last_used_at = timezone.now()

        api_key.save(
            update_fields=["last_used_at"]
        )

        return (api_key.user, None)