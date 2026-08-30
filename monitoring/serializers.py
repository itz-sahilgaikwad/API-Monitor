from rest_framework import serializers

from .models import APIMonitor, Incident


# =============================================================================
# API MONITOR SERIALIZER
# =============================================================================

class APIMonitorSerializer(serializers.ModelSerializer):

    has_api_key = serializers.SerializerMethodField(
        read_only=True
    )

    class Meta:
        model = APIMonitor

        fields = [
            # Identity
            "id",
            "name",
            "url",
            "method",
            "expected_status",

            # Ownership
            "owner",

            # Monitoring state
            "is_active",
            "status",
            "failure_count",
            "response_time",
            "last_error",
            "last_checked_at",
            "uptime_percentage",

            # Slow response
            "response_time_threshold_ms",

            # Contact
            "phone_number",

            # Authentication
            "auth_type",
            "api_key",
            "has_api_key",

            # Custom request headers
            "request_headers",

            # Request body
            "request_body",

            # Response validation
            "response_validation_type",
            "expected_response",

            # Downtime
            "downtime_started_at",
            "last_downtime_duration",

            # Monitoring
            "check_interval",
        ]

        # ---------------------------------------------------------------------
        # Fields controlled by the backend
        # ---------------------------------------------------------------------

        read_only_fields = [
            "id",

            # IMPORTANT:
            # The client can NEVER choose or change the owner.
            "owner",

            # Runtime fields
            "status",
            "failure_count",
            "response_time",
            "last_error",
            "last_checked_at",
            "uptime_percentage",

            # Downtime fields
            "downtime_started_at",
            "last_downtime_duration",

            # Computed field
            "has_api_key",
        ]

        extra_kwargs = {
            "api_key": {
                "write_only": True,
                "required": False,
                "allow_blank": True,
                "allow_null": True,
            },

            "request_headers": {
                "required": False,
            },

            "request_body": {
                "required": False,
                "allow_blank": True,
            },

            "response_validation_type": {
                "required": False,
            },

            "expected_response": {
                "required": False,
                "allow_blank": True,
            },
        }

    # =========================================================================
    # NORMALIZE FRONTEND AUTHENTICATION VALUE
    # =========================================================================

    def to_internal_value(self, data):

        # request.data can be immutable.
        data = data.copy()

        auth_type = data.get(
            "auth_type"
        )

        if auth_type:

            auth_type_map = {

                # X-API-Key
                "X-API-Key": "x_api_key",
                "x-api-key": "x_api_key",
                "x_api_key": "x_api_key",

                # Bearer
                "Bearer API Key": "bearer",
                "Bearer": "bearer",
                "bearer": "bearer",

                # No authentication
                "No Authentication": "none",
                "None": "none",
                "none": "none",
            }

            data["auth_type"] = auth_type_map.get(
                auth_type,
                auth_type
            )

        return super().to_internal_value(
            data
        )

    # =========================================================================
    # API KEY STATUS
    # =========================================================================

    def get_has_api_key(
        self,
        obj
    ):
        return bool(
            obj.api_key
        )

    # =========================================================================
    # VALIDATION
    # =========================================================================

    def validate(
        self,
        attrs
    ):

        auth_type = attrs.get(
            "auth_type",
            getattr(
                self.instance,
                "auth_type",
                "none"
            )
        )

        api_key_provided = (
            "api_key" in attrs
        )

        api_key = attrs.get(
            "api_key"
        )

        existing_key = (
            getattr(
                self.instance,
                "api_key",
                None
            )
            if self.instance
            else None
        )

        # =====================================================================
        # SECURITY: NEVER ACCEPT OWNER FROM CLIENT
        # =====================================================================

        # Even though owner is read_only, explicitly remove it if somehow
        # injected into serializer data.
        attrs.pop(
            "owner",
            None
        )

        # =====================================================================
        # RESPONSE VALIDATION
        # =====================================================================

        validation_type = attrs.get(
            "response_validation_type",
            getattr(
                self.instance,
                "response_validation_type",
                "none"
            )
        )

        expected_response = attrs.get(
            "expected_response",
            getattr(
                self.instance,
                "expected_response",
                ""
            )
        )

        validation_type = str(
            validation_type
        ).strip().lower()

        # Only supported response validation types are allowed.
        allowed_validation_types = {
            "none",
            "contains",
            "exact",
            "json",
        }

        if validation_type not in allowed_validation_types:
            raise serializers.ValidationError({
                "response_validation_type": (
                    "Invalid response validation type. "
                    "Choose none, contains, exact, or json."
                )
            })

        # For validation types that require an expected response,
        # make sure the value is actually provided.
        if validation_type in {
            "contains",
            "exact",
            "json",
        }:

            if not str(expected_response).strip():
                raise serializers.ValidationError({
                    "expected_response": (
                        "Expected response is required when "
                        "response validation is enabled."
                    )
                })

        # JSON validation must contain valid JSON.
        if validation_type == "json":

            import json

            try:
                json.loads(
                    expected_response
                )
            except (
                TypeError,
                ValueError,
                json.JSONDecodeError
            ):
                raise serializers.ValidationError({
                    "expected_response": (
                        "Expected response must contain valid JSON "
                        "when JSON validation is selected."
                    )
                })

        # If validation is disabled, clear the expected response.
        if validation_type == "none":

            attrs["response_validation_type"] = "none"
            attrs["expected_response"] = ""

        # =====================================================================
        # NEW MONITOR
        # =====================================================================

        if self.instance is None:

            if auth_type in (
                "bearer",
                "x_api_key",
            ):

                if not api_key:

                    raise serializers.ValidationError({
                        "api_key": (
                            "An API key is required when "
                            "authentication is enabled."
                        )
                    })

        # =====================================================================
        # EXISTING MONITOR
        # =====================================================================

        else:

            if auth_type in (
                "bearer",
                "x_api_key",
            ):

                # -------------------------------------------------------------
                # New API key supplied
                # -------------------------------------------------------------

                if api_key_provided and api_key:

                    pass

                # -------------------------------------------------------------
                # Empty API key
                #
                # Empty means:
                # keep existing key if one exists.
                # -------------------------------------------------------------

                elif api_key_provided and not api_key:

                    if existing_key:

                        attrs.pop(
                            "api_key",
                            None
                        )

                    else:

                        raise serializers.ValidationError({
                            "api_key": (
                                "An API key is required "
                                "for this authentication type."
                            )
                        })

                # -------------------------------------------------------------
                # API key omitted
                #
                # Keep the existing key.
                # -------------------------------------------------------------

                elif not api_key_provided:

                    if not existing_key:

                        raise serializers.ValidationError({
                            "api_key": (
                                "An API key is required "
                                "for this authentication type."
                            )
                        })

        # =====================================================================
        # NO AUTHENTICATION
        # =====================================================================

        if auth_type == "none":

            attrs["api_key"] = None

        return attrs


# =============================================================================
# INCIDENT SERIALIZER
# =============================================================================

class IncidentSerializer(
    serializers.ModelSerializer
):

    monitor_name = serializers.CharField(
        source="monitor.name",
        read_only=True
    )

    monitor_url = serializers.CharField(
        source="monitor.url",
        read_only=True
    )

    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Incident

        fields = [
            # Identity
            "id",

            # Monitor
            "monitor",
            "monitor_name",
            "monitor_url",

            # Incident
            "status",
            "reason",

            # Timestamps
            "started_at",
            "resolved_at",

            # Duration
            "duration_seconds",
        ]

        # ---------------------------------------------------------------------
        # Incident data is generated by the monitoring backend.
        # Users should only be able to READ it.
        # ---------------------------------------------------------------------

        read_only_fields = [
            "id",
            "monitor",
            "monitor_name",
            "monitor_url",
            "status",
            "reason",
            "started_at",
            "resolved_at",
            "duration_seconds",
        ]

    # =========================================================================
    # INCIDENT DURATION
    # =========================================================================

    def get_duration_seconds(
        self,
        obj
    ):

        if (
            obj.resolved_at
            and obj.started_at
        ):

            duration = (
                obj.resolved_at
                - obj.started_at
            ).total_seconds()

            return round(
                duration,
                2
            )

        if obj.started_at:

            from django.utils import timezone

            duration = (
                timezone.now()
                - obj.started_at
            ).total_seconds()

            return round(
                duration,
                2
            )

        return 0