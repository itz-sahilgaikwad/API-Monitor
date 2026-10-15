from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient, APIRequestFactory
from rest_framework.exceptions import AuthenticationFailed

from .auth_backends import APIKeyAuthentication
from .models import APIKey, User


class AuthenticationRegressionTests(TestCase):

	def setUp(self):
		self.client = APIClient()
		self.password = "Strong-Test-Password-123!"
		self.user = User.objects.create_user(
			email="auth@example.com",
			password=self.password,
		)

	def login(self):
		return self.client.post(
			"/api/auth/login/",
			{
				"email": self.user.email,
				"password": self.password,
			},
			format="json",
		)

	def test_locked_user_login_returns_401(self):
		self.user.locked_until = timezone.now() + timedelta(minutes=15)
		self.user.save(update_fields=["locked_until"])

		response = self.login()

		self.assertEqual(response.status_code, 401)

	def test_inactive_user_login_returns_401(self):
		self.user.is_active = False
		self.user.save(update_fields=["is_active"])

		response = self.login()

		self.assertEqual(response.status_code, 401)

	def test_active_unlocked_user_login_returns_tokens(self):
		response = self.login()

		self.assertEqual(response.status_code, 200)
		self.assertIn("access", response.data)
		self.assertIn("refresh", response.data)

	def create_api_key(self):
		raw_key, prefix, key_hash = APIKey.generate()
		APIKey.objects.create(
			user=self.user,
			name="Test key",
			key_prefix=prefix,
			key_hash=key_hash,
		)
		return raw_key

	def authenticate_api_key(self, raw_key):
		request = APIRequestFactory().get(
			"/api/monitoring/",
			HTTP_AUTHORIZATION=f"Api-Key {raw_key}",
		)
		return APIKeyAuthentication().authenticate(request)

	def test_active_user_active_api_key_succeeds(self):
		raw_key = self.create_api_key()

		authenticated = self.authenticate_api_key(raw_key)

		self.assertIsNotNone(authenticated)
		self.assertEqual(authenticated[0], self.user)

	def test_inactive_user_active_api_key_is_rejected(self):
		raw_key = self.create_api_key()
		self.user.is_active = False
		self.user.save(update_fields=["is_active"])

		with self.assertRaises(AuthenticationFailed):
			self.authenticate_api_key(raw_key)

	def test_revoked_api_key_is_rejected(self):
		raw_key = self.create_api_key()
		APIKey.objects.filter(user=self.user).update(is_active=False)

		with self.assertRaises(AuthenticationFailed):
			self.authenticate_api_key(raw_key)

# Create your tests here.
