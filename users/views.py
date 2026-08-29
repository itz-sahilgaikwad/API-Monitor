import os

from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail
from django.utils.crypto import get_random_string

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.throttling import ScopedRateThrottle
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken

from .models import _log, APIKey, ActivityLog, Team, TeamMember


User = get_user_model()


# ============================================================
# JWT TOKEN HELPER
# ============================================================

def get_tokens(user):

    refresh = RefreshToken.for_user(user)

    access_token = str(refresh.access_token)
    refresh_token = str(refresh)

    return {
        "refresh": refresh_token,
        "access": access_token,
    }


# ============================================================
# REGISTER USER
# ============================================================

class RegisterUserView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")
        name = (request.data.get("name") or "").strip()
        mobile = (request.data.get("mobile_number") or "").strip()

        if not email or not password:

            return Response(
                {
                    "error": "Email and password required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        email = email.strip().lower()

        # Duplicate email addresses and mobile numbers are allowed.
        # A new account is created for every registration request.
        user = User.objects.create_user(
            email=email,
            password=password,
            name=name,
            mobile_number=mobile
        )

        _log(
            user,
            "REGISTER",
            request=request
        )

        tokens = get_tokens(user)

        return Response(
            {
                "message": "User registered successfully",

                "tokens": tokens,

                # Compatibility with frontend
                "access": tokens["access"],
                "refresh": tokens["refresh"],

                "email": user.email,

                "role": getattr(
                    user,
                    "role",
                    None
                ),
            },
            status=status.HTTP_201_CREATED
        )


# ============================================================
# USER LOGIN
# ============================================================

class UserLoginView(APIView):

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):

        # Support:
        # identifier
        # email_or_mobile
        # email
        # mobile

        identifier = (
            request.data.get("identifier")
            or request.data.get("email_or_mobile")
            or request.data.get("email")
            or request.data.get("mobile")
        )

        password = request.data.get("password")

        if not identifier or not password:
            return Response(
                {
                    "error": "Email/mobile and password are required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        identifier = identifier.strip()

        # ------------------------------------------------------------
        # FIND USER
        # ------------------------------------------------------------

        if "@" in identifier:
            candidates = User.objects.filter(
                email=identifier.lower()
            ).order_by("id")
        else:
            candidates = User.objects.filter(
                mobile_number=identifier
            ).order_by("id")

        # ------------------------------------------------------------
        # CHECK PASSWORD
        # ------------------------------------------------------------

        user = None

        # Multiple accounts may share the same email/mobile.
        # The password determines which account logs in.
        for candidate in candidates:
            if candidate.check_password(password):
                user = candidate
                break

        if not user:
            return Response(
                {
                    "error": "Invalid credentials"
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # ------------------------------------------------------------
        # GENERATE JWT TOKENS
        # ------------------------------------------------------------

        tokens = get_tokens(user)

        # ------------------------------------------------------------
        # UPDATE LAST LOGIN
        # ------------------------------------------------------------

        user.last_login_at = timezone.now()

        user.save(
            update_fields=[
                "last_login_at"
            ]
        )

        # ------------------------------------------------------------
        # ACTIVITY LOG
        # ------------------------------------------------------------

        _log(
            user,
            "LOGIN",
            request=request
        )

        # ------------------------------------------------------------
        # RESPONSE
        # ------------------------------------------------------------

        return Response(
            {
                "message": "Login successful",

                # Existing backend structure
                "tokens": tokens,

                # Frontend compatibility
                "access": tokens["access"],
                "refresh": tokens["refresh"],

                "email": user.email,

                "role": getattr(
                    user,
                    "role",
                    None
                ),
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# ADMIN LOGIN
# ============================================================

class AdminLoginView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = request.data.get("email")
        password = request.data.get("password")

        if not email or not password:

            return Response(
                {
                    "error": "Email and password are required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user = authenticate(
            request,
            username=email,
            password=password
        )

        if not user:

            return Response(
                {
                    "error": "Invalid credentials"
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        if not user.is_admin():

            return Response(
                {
                    "error": "Admin access only"
                },
                status=status.HTTP_403_FORBIDDEN
            )

        tokens = get_tokens(user)

        _log(
            user,
            "LOGIN",
            request=request
        )

        return Response(
            {
                "message": "Admin login successful",

                "tokens": tokens,

                "access": tokens["access"],
                "refresh": tokens["refresh"],

                "email": user.email,

                "role": getattr(
                    user,
                    "role",
                    None
                ),
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# VERIFY EMAIL
# ============================================================

class VerifyEmailView(APIView):

    permission_classes = [AllowAny]

    def get(self, request):

        token = request.query_params.get("token")

        if not token:

            return Response(
                {
                    "error": "Verification token required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            user = User.objects.get(
                email_verification_token=token
            )

        except User.DoesNotExist:

            return Response(
                {
                    "error": "Invalid token"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        user.email_verified = True

        user.email_verification_token = None

        user.save(
            update_fields=[
                "email_verified",
                "email_verification_token"
            ]
        )

        _log(
            user,
            "EMAIL_VERIFIED"
        )

        return Response(
            {
                "message": "Email verified successfully"
            }
        )


# ============================================================
# FORGOT PASSWORD
# ============================================================

class ForgotPasswordView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        email = (request.data.get("email") or "").strip().lower()

        if not email:

            return Response(
                {
                    "error": "Email is required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Use a case-insensitive lookup so the reset request still
        # works if the address was stored with different capitalization.
        try:

            user = User.objects.get(
                email__iexact=email
            )

        except User.DoesNotExist:

            # Do not reveal whether an email address is registered.
            print(
                f"PASSWORD RESET: no user found for {email}"
            )

            return Response(
                {
                    "message":
                        "If that email is registered, "
                        "a reset link has been sent."
                },
                status=status.HTTP_200_OK
            )

        # ========================================================
        # GENERATE SECURE RESET TOKEN
        # ========================================================

        reset_token = get_random_string(
            length=64
        )

        user.password_reset_token = reset_token

        user.password_reset_expires = (
            timezone.now()
            + timezone.timedelta(
                minutes=30
            )
        )

        user.save(
            update_fields=[
                "password_reset_token",
                "password_reset_expires"
            ]
        )

        # ========================================================
        # RESET URL
        # ========================================================

        # On the local development server, use the local frontend.
        # FRONTEND_BASE_URL can still override this through .env.
        frontend_base_url = os.getenv(
            "FRONTEND_BASE_URL",
            "http://127.0.0.1:8000"
        ).rstrip("/")

        reset_url = (
            f"{frontend_base_url}"
            f"/app/reset_password.html"
            f"?token={reset_token}"
        )

        # ========================================================
        # EMAIL
        # ========================================================

        subject = "Reset your API Monitor password"

        message = f"""Hello {user.name or "there"},

We received a request to reset your API Monitor password.

Use the link below to create a new password:

{reset_url}

This password reset link will expire in 30 minutes.

If you did not request this password reset, you can safely ignore this email.

Regards,
API Monitor
"""

        from_email = getattr(
            settings,
            "DEFAULT_FROM_EMAIL",
            None
        ) or getattr(
            settings,
            "EMAIL_HOST_USER",
            None
        )

        recipient_email = user.email

        print(
            "PASSWORD RESET: sending email "
            f"from={from_email!r} to={recipient_email!r}"
        )

        try:

            sent_count = send_mail(
                subject=subject,
                message=message,
                from_email=from_email,
                recipient_list=[recipient_email],
                fail_silently=False
            )

            print(
                "PASSWORD RESET: send_mail returned "
                f"{sent_count}"
            )

            if sent_count != 1:
                print(
                    "PASSWORD RESET: email backend reported "
                    "that the message was not sent."
                )

                return Response(
                    {
                        "error":
                            "Unable to send password reset email."
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except Exception as error:

            print(
                "PASSWORD RESET EMAIL ERROR:",
                repr(error)
            )

            return Response(
                {
                    "error":
                        "Unable to send password reset email."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response(
            {
                "message":
                    "Password reset link sent"
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# RESET PASSWORD
# ============================================================

class ResetPasswordView(APIView):

    permission_classes = [AllowAny]

    def post(self, request):

        token = request.data.get("token")
        password = request.data.get("password")

        if not token or not password:

            return Response(
                {
                    "error":
                        "Token and new password are required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )


        try:

            user = User.objects.get(
                password_reset_token=token
            )

        except User.DoesNotExist:

            return Response(
                {
                    "error": "Invalid or expired token"
                },
                status=status.HTTP_400_BAD_REQUEST
            )


        # ========================================================
        # CHECK EXPIRATION
        # ========================================================

        if (
            not user.password_reset_expires
            or
            user.password_reset_expires
            < timezone.now()
        ):

            user.password_reset_token = None

            user.password_reset_expires = None

            user.save(
                update_fields=[
                    "password_reset_token",
                    "password_reset_expires"
                ]
            )

            return Response(
                {
                    "error":
                        "Password reset link has expired"
                },
                status=status.HTTP_400_BAD_REQUEST
            )


        # ========================================================
        # SET NEW PASSWORD
        # ========================================================

        user.set_password(
            password
        )

        user.password_reset_token = None

        user.password_reset_expires = None

        user.save(
            update_fields=[
                "password",
                "password_reset_token",
                "password_reset_expires"
            ]
        )


        _log(
            user,
            "PASSWORD_RESET"
        )


        return Response(
            {
                "message":
                    "Password reset successful"
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# PROFILE
# ============================================================

class UserProfileView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        return Response(
            {
                "email": user.email,
                "name": user.name,
                "mobile": user.mobile_number,
                "role": user.role,
                "email_alerts_enabled": user.email_alerts_enabled,
                "sms_alerts_enabled": user.sms_alerts_enabled
            }
        )

    def patch(self, request):
        user = request.user

        if "email_alerts_enabled" in request.data:
            user.email_alerts_enabled = bool(request.data.get("email_alerts_enabled"))

        if "sms_alerts_enabled" in request.data:
            user.sms_alerts_enabled = bool(request.data.get("sms_alerts_enabled"))

        user.save(
            update_fields=[
                "email_alerts_enabled",
                "sms_alerts_enabled"
            ]
        )

        return Response(
            {
                "message": "Notification preferences updated.",
                "email_alerts_enabled": user.email_alerts_enabled,
                "sms_alerts_enabled": user.sms_alerts_enabled
            }
        )


# ============================================================
# NOTIFICATION PREFERENCES
# ============================================================

class NotificationPrefsView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        return Response(
            {
                "email_alerts":
                    user.email_alerts_enabled,

                "sms_alerts":
                    user.sms_alerts_enabled
            }
        )


# ============================================================
# ACTIVITY LOGS
# ============================================================

class ActivityLogView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        logs = ActivityLog.objects.filter(
            user=request.user
        )[:50]

        data = [
            {
                "action": log.action,
                "resource": log.resource,
                "timestamp": log.timestamp
            }
            for log in logs
        ]

        return Response(data)


# ============================================================
# LOGOUT
# ============================================================

class LogoutView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request):

        user = request.user

        try:

            refresh_token = request.data.get(
                "refresh"
            )

            if refresh_token:

                token = RefreshToken(
                    refresh_token
                )

                token.blacklist()

        except Exception:

            pass

        _log(
            user,
            "LOGOUT",
            request=request
        )

        return Response(
            {
                "message":
                    "Logout successful"
            }
        )


# ============================================================
# API KEYS - LIST AND CREATE
# ============================================================

class APIKeyListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        keys = APIKey.objects.filter(
            user=request.user
        )

        data = [
            {
                "id": k.id,
                "name": k.name,
                "prefix": k.key_prefix,
                "created_at": k.created_at,
                "last_used": k.last_used_at,
                "active": k.is_active
            }
            for k in keys
        ]

        return Response(data)

    def post(self, request):

        name = request.data.get(
            "name",
            "My API Key"
        )

        raw, prefix, hashed = (
            APIKey.generate()
        )

        key = APIKey.objects.create(
            user=request.user,
            name=name,
            key_prefix=prefix,
            key_hash=hashed
        )

        return Response(
            {
                "message":
                    "API key created",

                "api_key":
                    raw
            },
            status=status.HTTP_201_CREATED
        )


# ============================================================
# API KEY REVOKE
# ============================================================

class APIKeyRevokeView(APIView):

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):

        try:

            key = APIKey.objects.get(
                pk=pk,
                user=request.user
            )

        except APIKey.DoesNotExist:

            return Response(
                {
                    "error":
                        "API key not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        key.is_active = False

        key.save(
            update_fields=[
                "is_active"
            ]
        )

        return Response(
            {
                "message":
                    "API key revoked"
            }
        )


# ============================================================
# TEAMS - LIST AND CREATE
# ============================================================

class TeamListCreateView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request):

        teams = Team.objects.filter(
            owner=request.user
        )

        data = [
            {
                "id": t.id,
                "name": t.name,
                "created_at": t.created_at
            }
            for t in teams
        ]

        return Response(data)

    def post(self, request):

        name = request.data.get(
            "name"
        )

        if not name:

            return Response(
                {
                    "error":
                        "Team name required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        team = Team.objects.create(
            owner=request.user,
            name=name
        )

        return Response(
            {
                "message":
                    "Team created",

                "team_id":
                    team.id
            },
            status=status.HTTP_201_CREATED
        )


# ============================================================
# TEAM MEMBERS
# ============================================================

class TeamMembersView(APIView):

    permission_classes = [IsAuthenticated]

    def get(self, request, team_id):

        try:

            team = Team.objects.get(
                id=team_id,
                owner=request.user
            )

        except Team.DoesNotExist:

            return Response(
                {
                    "error":
                        "Team not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        members = TeamMember.objects.filter(
            team=team
        )

        data = [
            {
                "user_id": m.user.id,
                "email": m.user.email,
                "role": m.role
            }
            for m in members
        ]

        return Response(data)


# ============================================================
# INVITE USER TO TEAM
# ============================================================

class TeamInviteView(APIView):

    permission_classes = [IsAuthenticated]

    def post(self, request, team_id):

        email = request.data.get(
            "email"
        )

        if not email:

            return Response(
                {
                    "error":
                        "Email required"
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            team = Team.objects.get(
                id=team_id,
                owner=request.user
            )

        except Team.DoesNotExist:

            return Response(
                {
                    "error":
                        "Team not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        try:

            user = User.objects.get(
                email=email
            )

        except User.DoesNotExist:

            return Response(
                {
                    "error":
                        "User not found"
                },
                status=status.HTTP_404_NOT_FOUND
            )

        TeamMember.objects.create(
            team=team,
            user=user,
            role="member"
        )

        return Response(
            {
                "message":
                    "User added to team"
            }
        )


# ============================================================
# ADMIN TEST ENDPOINT
# ============================================================

class AdminOnlyTestView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsAdminUser
    ]

    def get(self, request):

        return Response(
            {
                "message":
                    "Admin access granted",

                "admin":
                    request.user.email
            }
        )


# ============================================================
# ADMIN - LIST ALL USERS
# ============================================================

class AdminUserListView(APIView):

    permission_classes = [
        IsAuthenticated,
        IsAdminUser
    ]

    def get(self, request):

        users = User.objects.all()

        data = [
            {
                "id": u.id,
                "email": u.email,
                "mobile": u.mobile,
                "is_active": u.is_active,
                "is_staff": u.is_staff,
                "date_joined": u.date_joined
            }
            for u in users
        ]

        return Response(data)