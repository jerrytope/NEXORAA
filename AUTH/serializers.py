import re
from django.contrib.auth import authenticate
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from AUTH.models import User, EmailVerification, Country


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_password_strength(password):
    """
    Reusable password strength validator.
    Enforces: min 8 chars, 1 uppercase, 1 lowercase, 1 digit, 1 special char.
    """
    errors = []
    if len(password) < 8:
        errors.append("Password must be at least 8 characters.")
    if not re.search(r'[A-Z]', password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r'[a-z]', password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r'\d', password):
        errors.append("Password must contain at least one number.")
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        errors.append("Password must contain at least one special character.")
    if errors:
        raise serializers.ValidationError(errors)
    return password


# ---------------------------------------------------------------------------
# Country
# ---------------------------------------------------------------------------

class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ('id', 'name', 'code', 'phone_code', 'flag_emoji',
                  'currency_code', 'currency_symbol')


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Extends the default JWT payload to include role, email,
    full_name, and is_verified.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['email'] = user.email
        token['role'] = user.role
        token['full_name'] = user.full_name
        token['is_verified'] = user.is_verified
        return token

    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')

        if not email or not password:
            raise serializers.ValidationError("Email and password are required.")

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise AuthenticationFailed("Invalid email or password.")

        if not user.check_password(password):
            raise AuthenticationFailed("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationFailed("Account is disabled.")

        if not user.is_verified:
            raise AuthenticationFailed("Email not verified.")

        return super().validate(attrs)


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)
    country = CountrySerializer(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'first_name',
            'last_name',
            'full_name',
            'role',
            'contact_person',
            'contact_person_number',
            'brand_name',
            'country',
            'referral_code',
            'agree_to_terms',
            'is_active',
            'is_verified',
            'date_joined',
        )
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

class RegisterSerializer(serializers.Serializer):
    # --- Auth ---
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    password_confirmation = serializers.CharField(write_only=True)

    # --- Role ---
    role = serializers.ChoiceField(choices=User.Role.choices)

    # --- Shared profile fields ---
    contact_person = serializers.CharField(max_length=150)
    contact_person_number = serializers.CharField(max_length=30)
    country = serializers.PrimaryKeyRelatedField(
        queryset=Country.objects.filter(is_active=True)
    )

    # --- Brand only ---
    brand_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    # --- Optional ---
    referral_code = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=None
    )
    agree_to_terms = serializers.BooleanField(default=True)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            # Raise as a dict so the view can detect and return 409
            raise serializers.ValidationError("email_exists")
        return value

    def validate_password(self, value):
        return validate_password_strength(value)

    def validate(self, data):
        # Password confirmation check
        if data['password'] != data['password_confirmation']:
            raise serializers.ValidationError(
                {"password_confirmation": "Passwords do not match."}
            )

        # brand_name required for brand role
        if data['role'] == User.Role.BRAND and not data.get('brand_name'):
            raise serializers.ValidationError(
                {"brand_name": "brand_name is required for brand registration."}
            )

        # agree_to_terms must be True
        if not data.get('agree_to_terms', False):
            raise serializers.ValidationError(
                {"agree_to_terms": "You must agree to the terms to register."}
            )

        return data

    def create(self, validated_data):
        # Remove non-model fields
        validated_data.pop('password_confirmation')
        password = validated_data.pop('password')

        # Clean up optional fields
        referral_code = validated_data.pop('referral_code', None) or None
        brand_name = validated_data.pop('brand_name', None) or None

        user = User.objects.create_user(
            password=password,
            is_verified=False,
            is_active=False,
            referral_code=referral_code,
            brand_name=brand_name,
            **validated_data,
        )
        return user


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------

class EmailVerificationSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    verification_code = serializers.CharField(max_length=6)

    def validate(self, data):
        try:
            user = User.objects.get(id=data['user_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid user.")

        try:
            verification = EmailVerification.objects.get(
                user=user,
                code=data['verification_code'],
                is_used=False,
                purpose=EmailVerification.Purpose.EMAIL_VERIFICATION,
            )
        except EmailVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired code.")

        if verification.is_expired():
            raise serializers.ValidationError("Verification code has expired.")

        data['user'] = user
        data['verification'] = verification
        return data

    def save(self):
        user = self.validated_data['user']
        verification = self.validated_data['verification']

        verification.mark_used()

        # Activate the account on successful verification
        user.is_verified = True
        user.is_active = True
        user.save(update_fields=['is_verified', 'is_active'])

        return user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        email = data.get('email')
        password = data.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Keep error generic to prevent email enumeration
            raise AuthenticationFailed("Invalid email or password.")

        if not user.check_password(password):
            raise AuthenticationFailed("Invalid email or password.")

        if not user.is_verified:
            raise serializers.ValidationError(
                {"code": "email_not_verified", "detail": "Email not verified."}
            )

        if not user.is_active:
            raise serializers.ValidationError(
                {"code": "account_disabled", "detail": "Account is disabled."}
            )

        data['user'] = user
        return data


# ---------------------------------------------------------------------------
# Resend Verification Code
# ---------------------------------------------------------------------------

class ResendCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        try:
            user = User.objects.get(email=data['email'])
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")

        if user.is_verified:
            raise serializers.ValidationError("This account is already verified.")

        self.context['user'] = user
        return data


# ---------------------------------------------------------------------------
# Password Reset — Request
# ---------------------------------------------------------------------------

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate(self, data):
        # Always passes — no enumeration leak.
        # The view will silently skip sending if user doesn't exist.
        try:
            user = User.objects.get(email=data['email'])
            self.context['user'] = user
        except User.DoesNotExist:
            self.context['user'] = None
        return data


# ---------------------------------------------------------------------------
# Password Reset — Confirm
# ---------------------------------------------------------------------------

class PasswordResetConfirmSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    code = serializers.CharField(max_length=6)
    new_password = serializers.CharField(write_only=True)
    new_password_confirmation = serializers.CharField(write_only=True)

    def validate_new_password(self, value):
        return validate_password_strength(value)

    def validate(self, data):
        if data['new_password'] != data['new_password_confirmation']:
            raise serializers.ValidationError(
                {"new_password_confirmation": "Passwords do not match."}
            )

        try:
            user = User.objects.get(id=data['user_id'])
        except User.DoesNotExist:
            raise serializers.ValidationError("Invalid user.")

        try:
            verification = EmailVerification.objects.get(
                user=user,
                code=data['code'],
                is_used=False,
                purpose=EmailVerification.Purpose.PASSWORD_RESET,
            )
        except EmailVerification.DoesNotExist:
            raise serializers.ValidationError("Invalid or expired code.")

        if verification.is_expired():
            raise serializers.ValidationError("Reset code has expired.")

        data['user'] = user
        data['verification'] = verification
        return data

    def save(self):
        user = self.validated_data['user']
        verification = self.validated_data['verification']

        # Mark code used
        verification.mark_used()

        # Set new password
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])

        # Invalidate all existing refresh tokens by rotating the secret
        # This works if you use token blacklisting — the view handles it
        return user