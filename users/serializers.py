from rest_framework import serializers
from .models import User, ActivityLog, APIKey, Team, TeamMember, TeamMonitor


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model  = User
        fields = ['email', 'name', 'mobile_number', 'password']

    def validate_email(self, value):
        if User.objects.filter(email=value.lower()).exists():
            raise serializers.ValidationError("An account with this email already exists.")
        return value.lower()

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'email', 'name', 'mobile_number', 'role',
            'email_verified', 'created_at',
            'email_alerts_enabled', 'sms_alerts_enabled',
            'response_time_threshold_ms', 'alert_cooldown_minutes',
        ]
        read_only_fields = ('email', 'role', 'email_verified', 'created_at')


class NotificationPrefsSerializer(serializers.ModelSerializer):
    class Meta:
        model  = User
        fields = [
            'email_alerts_enabled', 'sms_alerts_enabled',
            'response_time_threshold_ms', 'alert_cooldown_minutes',
        ]


class ActivityLogSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ActivityLog
        fields = ['id', 'action', 'resource', 'ip_address', 'timestamp']


class APIKeySerializer(serializers.ModelSerializer):
    class Meta:
        model  = APIKey
        fields = ['id', 'name', 'key_prefix', 'created_at', 'last_used_at', 'is_active']
        read_only_fields = ['key_prefix', 'created_at', 'last_used_at']


class TeamSerializer(serializers.ModelSerializer):
    owner_email   = serializers.CharField(source='owner.email', read_only=True)
    member_count  = serializers.SerializerMethodField()

    class Meta:
        model  = Team
        fields = ['id', 'name', 'owner_email', 'member_count', 'created_at']
        read_only_fields = ['owner_email', 'created_at']

    def get_member_count(self, obj):
        return obj.members.count()


class TeamMemberSerializer(serializers.ModelSerializer):
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model  = TeamMember
        fields = ['id', 'user_email', 'role']