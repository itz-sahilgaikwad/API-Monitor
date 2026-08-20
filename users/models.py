from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone
import secrets
import hashlib


# ── User Manager ──────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("Email is required")

        email = self.normalize_email(email)

        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)

        return user


    def create_superuser(self, email, password=None, **extra_fields):

        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')
        extra_fields.setdefault('email_verified', True)

        return self.create_user(email, password, **extra_fields)



# ── User Model ─────────────────────────────────────────────────────────────────

class User(AbstractBaseUser, PermissionsMixin):

    ROLE_CHOICES = (
        ('ADMIN', 'admin'),
        ('USER',  'user'),
    )

    email = models.EmailField(unique=True, db_index=True)

    name = models.CharField(
        max_length=150,
        blank=True,
        default=''
    )

    mobile_number = models.CharField(
        max_length=15,
        unique=True,
        null=True,
        blank=True,
        db_index=True
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='USER'
    )

    is_active = models.BooleanField(default=True)

    is_staff = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    last_login_at = models.DateTimeField(null=True, blank=True)



    # ── Email verification ─────────────────────────────────────────

    email_verified = models.BooleanField(default=False)

    email_verification_token = models.CharField(
        max_length=64,
        null=True,
        blank=True
    )



    # ── Password reset ─────────────────────────────────────────────

    password_reset_token = models.CharField(
        max_length=64,
        null=True,
        blank=True
    )

    password_reset_expires = models.DateTimeField(
        null=True,
        blank=True
    )



    # ── Brute-force protection ─────────────────────────────────────

    login_attempts = models.IntegerField(default=0)

    locked_until = models.DateTimeField(
        null=True,
        blank=True
    )



    # ── Notification preferences ───────────────────────────────────

    email_alerts_enabled = models.BooleanField(default=True)

    sms_alerts_enabled = models.BooleanField(default=True)

    response_time_threshold_ms = models.IntegerField(default=1000)

    alert_cooldown_minutes = models.IntegerField(default=10)

    last_alert_sent_at = models.DateTimeField(null=True, blank=True)



    objects = UserManager()

    USERNAME_FIELD = 'email'

    REQUIRED_FIELDS = []



    def __str__(self):
        return self.email



    # ── Login Identifier (Email OR Mobile) ─────────────────────────

    @staticmethod
    def find_by_login(identifier):

        if "@" in identifier:
            return User.objects.filter(email=identifier).first()

        return User.objects.filter(mobile_number=identifier).first()



    # ── Admin helper ───────────────────────────────────────────────

    def is_admin(self):
        return self.role == "ADMIN"



    # ── Security Lock Check ────────────────────────────────────────

    def is_locked(self):

        if self.locked_until and timezone.now() < self.locked_until:
            return True

        return False



    # ── Failed Login Tracking ──────────────────────────────────────

    def record_failed_login(self, request=None):

        self.login_attempts += 1

        if self.login_attempts >= 5:
            self.locked_until = timezone.now() + timezone.timedelta(minutes=15)
            self.login_attempts = 0

        self.save(update_fields=['login_attempts', 'locked_until'])

        _log(self, "LOGIN_FAILED", request=request)



    # ── Clear Attempts After Success ───────────────────────────────

    def clear_login_attempts(self):

        self.login_attempts = 0
        self.locked_until = None

        self.save(update_fields=['login_attempts', 'locked_until'])



    # ── Alert Cooldown ─────────────────────────────────────────────

    def can_send_alert(self):

        if not self.last_alert_sent_at:
            return True

        elapsed = (timezone.now() - self.last_alert_sent_at).total_seconds() / 60

        return elapsed >= self.alert_cooldown_minutes



    def mark_alert_sent(self):

        self.last_alert_sent_at = timezone.now()

        self.save(update_fields=['last_alert_sent_at'])



# ── Activity Log ──────────────────────────────────────────────────────────────

class ActivityLog(models.Model):

    ACTION_CHOICES = [
        ('REGISTER',        'Register'),
        ('LOGIN',           'Login'),
        ('LOGOUT',          'Logout'),
        ('LOGIN_FAILED',    'Login Failed'),
        ('MONITOR_CREATED', 'Monitor Created'),
        ('MONITOR_DELETED', 'Monitor Deleted'),
        ('MONITOR_TOGGLED', 'Monitor Toggled'),
        ('PASSWORD_RESET',  'Password Reset'),
        ('EMAIL_VERIFIED',  'Email Verified'),
        ('API_KEY_CREATED', 'API Key Created'),
        ('API_KEY_REVOKED', 'API Key Revoked'),
        ('TEAM_CREATED',    'Team Created'),
        ('MEMBER_INVITED',  'Member Invited'),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='activity_logs',
        null=True,
        blank=True
    )

    action = models.CharField(max_length=32, choices=ACTION_CHOICES)

    resource = models.CharField(
        max_length=200,
        blank=True,
        default=''
    )

    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True
    )

    timestamp = models.DateTimeField(auto_now_add=True)



    class Meta:
        ordering = ['-timestamp']



    def __str__(self):
        return f"{self.user} — {self.action}"



def _log(user, action, resource='', request=None):

    ip = None

    if request:
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')

        ip = x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')

    ActivityLog.objects.create(
        user=user,
        action=action,
        resource=resource,
        ip_address=ip
    )



# ── API Key ───────────────────────────────────────────────────────────────────

class APIKey(models.Model):

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='api_keys'
    )

    name = models.CharField(max_length=100, default='My API Key')

    key_prefix = models.CharField(max_length=8)

    key_hash = models.CharField(max_length=64)

    created_at = models.DateTimeField(auto_now_add=True)

    last_used_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=True)



    def __str__(self):
        return f"{self.user.email} — {self.name} ({self.key_prefix}…)"


    @staticmethod
    def generate():

        raw = secrets.token_urlsafe(48)

        prefix = raw[:8]

        hashed = hashlib.sha256(raw.encode()).hexdigest()

        return raw, prefix, hashed


    @staticmethod
    def hash_key(raw_key):

        return hashlib.sha256(raw_key.encode()).hexdigest()



# ── Teams ─────────────────────────────────────────────────────────────────────

class Team(models.Model):

    name = models.CharField(max_length=100)

    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_teams'
    )

    created_at = models.DateTimeField(auto_now_add=True)


    def __str__(self):

        return f"{self.name} (owner: {self.owner.email})"



class TeamMember(models.Model):

    ROLE_CHOICES = [
        ('OWNER',  'Owner'),
        ('EDITOR', 'Editor'),
        ('VIEWER', 'Viewer'),
    ]

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='members'
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='team_memberships'
    )

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='VIEWER'
    )

    class Meta:
        unique_together = ('team', 'user')


    def __str__(self):

        return f"{self.user.email} in {self.team.name} ({self.role})"



class TeamMonitor(models.Model):

    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name='team_monitors'
    )

    monitor = models.ForeignKey(
        'monitoring.APIMonitor',
        on_delete=models.CASCADE,
        related_name='team_monitors'
    )

    class Meta:
        unique_together = ('team', 'monitor')


    def __str__(self):

        return f"{self.monitor.name} in {self.team.name}"