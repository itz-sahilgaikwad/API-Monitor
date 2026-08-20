from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views


urlpatterns = [

    # ─────────────────────────────────────────────────────────
    # AUTHENTICATION
    # ─────────────────────────────────────────────────────────

    path(
        'register/',
        views.RegisterUserView.as_view(),
        name='register'
    ),

    path(
        'login/',
        views.UserLoginView.as_view(),
        name='login'
    ),

    path(
        'logout/',
        views.LogoutView.as_view(),
        name='logout'
    ),

    path(
        'token/refresh/',
        TokenRefreshView.as_view(),
        name='token-refresh'
    ),


    # ─────────────────────────────────────────────────────────
    # EMAIL VERIFICATION
    # ─────────────────────────────────────────────────────────

    path(
        'verify-email/',
        views.VerifyEmailView.as_view(),
        name='verify-email'
    ),


    # ─────────────────────────────────────────────────────────
    # PASSWORD RESET
    # ─────────────────────────────────────────────────────────

    path(
        'forgot-password/',
        views.ForgotPasswordView.as_view(),
        name='forgot-password'
    ),

    path(
        'reset-password/',
        views.ResetPasswordView.as_view(),
        name='reset-password'
    ),


    # ─────────────────────────────────────────────────────────
    # PROFILE & PREFERENCES
    # ─────────────────────────────────────────────────────────

    path(
        'profile/',
        views.UserProfileView.as_view(),
        name='profile'
    ),

    path(
        'preferences/',
        views.NotificationPrefsView.as_view(),
        name='preferences'
    ),


    # ─────────────────────────────────────────────────────────
    # ACTIVITY LOGS
    # ─────────────────────────────────────────────────────────

    path(
        'activity-log/',
        views.ActivityLogView.as_view(),
        name='activity-log'
    ),


    # ─────────────────────────────────────────────────────────
    # API KEYS
    # ─────────────────────────────────────────────────────────

    path(
        'api-keys/',
        views.APIKeyListCreateView.as_view(),
        name='api-keys'
    ),

    path(
        'api-keys/<int:pk>/',
        views.APIKeyRevokeView.as_view(),
        name='api-key-revoke'
    ),


    # ─────────────────────────────────────────────────────────
    # TEAMS
    # ─────────────────────────────────────────────────────────

    path(
        'teams/',
        views.TeamListCreateView.as_view(),
        name='teams'
    ),

    path(
        'teams/<int:team_id>/invite/',
        views.TeamInviteView.as_view(),
        name='team-invite'
    ),

    path(
        'teams/<int:team_id>/members/',
        views.TeamMembersView.as_view(),
        name='team-members'
    ),

]