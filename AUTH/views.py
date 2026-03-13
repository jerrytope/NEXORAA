import logging
from django.conf import settings
from django.utils import timezone
from django.core.mail import send_mail
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.generics import GenericAPIView, ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from drf_spectacular.utils import extend_schema, OpenApiResponse
from django_ratelimit.decorators import ratelimit
from django.utils.decorators import method_decorator

from AUTH.models import User, EmailVerification, Country
from .serializers import (
    RegisterSerializer,
    EmailVerificationSerializer,
    MyTokenObtainPairSerializer,
    UserSerializer,
    LoginSerializer,
    ResendCodeSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
    CountrySerializer,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Email Utility
# ---------------------------------------------------------------------------

EMAIL_TEMPLATES = {
    'verification': {
        'subject': 'Verify Your Email - NEXORA',
        'body': (
            "Hello {name},\n\n"
            "Your email verification code is:\n\n"
            "  {code}\n\n"
            "This code will expire in 5 minutes.\n\n"
            "Thank you for registering with NEXORA!"
        ),
    },
    'password_reset': {
        'subject': 'Password Reset Code - NEXORA',
        'body': (
            "Hello {name},\n\n"
            "You requested a password reset. Your code is:\n\n"
            "  {code}\n\n"
            "⚠️ This code will expire in 5 minutes.\n\n"
            "If you did not request this, please ignore this email.\n"
            "Do not share this code with anyone."
        ),
    },
    'resend_verification': {
        'subject': 'New Verification Code - NEXORA',
        'body': (
            "Hello {name},\n\n"
            "Here is your new verification code:\n\n"
            "  {code}\n\n"
            "⚠️ This code will expire in 5 minutes.\n\n"
            "If you did not request this, please ignore this email."
        ),
    },
}


def send_email(user, code, template_key='verification'):
    template = EMAIL_TEMPLATES[template_key]
    subject = template['subject']
    name = user.first_name or user.contact_person or user.email
    body = template['body'].format(name=name, code=code)

    try:
        if settings.DEBUG:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=False,
            )
        else:
            msg = MIMEMultipart()
            msg['From'] = settings.EMAIL_HOST_USER
            msg['To'] = user.email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            with smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT) as server:
                server.starttls()
                server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
                server.send_message(msg)
    except Exception as e:
        logger.error(f"Email send failed [{template_key}] to {user.email}: {e}")
        raise


def _issue_tokens(user):
    """
    Generate a JWT access + refresh token pair for the given user
    and return a response-ready dict including the full user object.
    """
    refresh = RefreshToken.for_user(user)

    # Embed custom claims to match MyTokenObtainPairSerializer
    refresh['email'] = user.email
    refresh['role'] = user.role
    refresh['full_name'] = user.full_name
    refresh['is_verified'] = user.is_verified

    return {
        'access_token': str(refresh.access_token),
        'refresh_token': str(refresh),
        'user': UserSerializer(user).data,
    }


# ---------------------------------------------------------------------------
# Register
# ---------------------------------------------------------------------------

@method_decorator(
    ratelimit(key='ip', rate='3/15m', method='POST', block=True),
    name='dispatch',
)
class RegisterView(APIView):
    serializer_class = RegisterSerializer

    @extend_schema(
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="Registered successfully"),
            400: OpenApiResponse(description="Validation error"),
            409: OpenApiResponse(description="Email already exists"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        }
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)

        # Detect email conflict before full validation to return 409
        if not serializer.is_valid():
            errors = serializer.errors
            email_errors = errors.get('email', [])
            if any('email_exists' in str(e) for e in email_errors):
                return Response(
                    {"error": "An account with this email already exists."},
                    status=status.HTTP_409_CONFLICT,
                )
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.save()

        code = EmailVerification.generate_code()
        EmailVerification.objects.create(
            user=user,
            code=code,
            purpose=EmailVerification.Purpose.EMAIL_VERIFICATION,
        )

        try:
            send_email(user, code, template_key='verification')
        except Exception:
            # User is created — email failure is non-fatal, log already captured
            pass

        return Response(
            {
                "message": "Registration successful. Check your email for a verification code.",
                "user_id": user.id,
            },
            status=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------

class EmailVerificationView(GenericAPIView):
    serializer_class = EmailVerificationSerializer

    @extend_schema(
        request=EmailVerificationSerializer,
        responses={
            200: OpenApiResponse(description="Email verified successfully"),
            400: OpenApiResponse(description="Invalid or expired code"),
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": "Email verified. You can now log in."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Resend Verification Code
# ---------------------------------------------------------------------------

class ResendVerificationView(GenericAPIView):
    serializer_class = ResendCodeSerializer

    @extend_schema(
        request=ResendCodeSerializer,
        responses={
            200: OpenApiResponse(description="Verification code resent"),
            400: OpenApiResponse(description="Bad request"),
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context['user']

        code = EmailVerification.generate_code()
        verification = EmailVerification.objects.create(
            user=user,
            code=code,
            purpose=EmailVerification.Purpose.EMAIL_VERIFICATION,
        )

        try:
            send_email(user, code, template_key='resend_verification')
        except Exception:
            return Response(
                {"error": "Code created but email failed to send. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "message": "Verification code resent successfully.",
                "user_id": user.id,
                "expires_at": verification.expires_at,
            },
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

@method_decorator(
    ratelimit(key='ip', rate='5/15m', method='POST', block=True),
    name='dispatch',
)
class LoginView(APIView):
    serializer_class = LoginSerializer

    @extend_schema(
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Login successful"),
            401: OpenApiResponse(description="Invalid credentials"),
            403: OpenApiResponse(description="Email not verified"),
            429: OpenApiResponse(description="Too many failed attempts"),
        }
    )
    def post(self, request):
        serializer = self.serializer_class(data=request.data)

        if not serializer.is_valid():
            errors = serializer.errors

            # Map coded errors to correct HTTP status
            non_field = errors.get('non_field_errors', [])
            for error in non_field:
                if isinstance(error, dict):
                    if error.get('code') == 'email_not_verified':
                        return Response(
                            {"error": "Please verify your email before logging in."},
                            status=status.HTTP_403_FORBIDDEN,
                        )
                    if error.get('code') == 'account_disabled':
                        return Response(
                            {"error": "Your account has been disabled."},
                            status=status.HTTP_403_FORBIDDEN,
                        )

            return Response(
                {"error": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        user = serializer.validated_data['user']
        return Response(_issue_tokens(user), status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Token Refresh
# ---------------------------------------------------------------------------

class TokenRefreshViewCustom(TokenRefreshView):
    pass


# ---------------------------------------------------------------------------
# Token Obtain (direct JWT — kept for API clients)
# ---------------------------------------------------------------------------

class TokenObtainPairViewCustom(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            205: OpenApiResponse(description="Logged out successfully"),
            400: OpenApiResponse(description="Invalid or missing refresh token"),
        }
    )
    def post(self, request):
        refresh_token = request.data.get('refresh_token')

        if not refresh_token:
            return Response(
                {"error": "refresh_token is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError as e:
            return Response(
                {"error": "Invalid or expired token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {"message": "Logged out successfully."},
            status=status.HTTP_205_RESET_CONTENT,
        )


# ---------------------------------------------------------------------------
# Me
# ---------------------------------------------------------------------------

class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user profile",
        responses={
            200: UserSerializer,
            401: OpenApiResponse(description="Unauthorized"),
        }
    )
    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ---------------------------------------------------------------------------
# Password Reset — Request
# ---------------------------------------------------------------------------

@method_decorator(
    ratelimit(key='post:email', rate='3/h', method='POST', block=True),
    name='dispatch',
)
class PasswordResetRequestView(GenericAPIView):
    serializer_class = PasswordResetRequestSerializer

    @extend_schema(
        request=PasswordResetRequestSerializer,
        responses={
            200: OpenApiResponse(description="Reset code sent if account exists"),
            429: OpenApiResponse(description="Rate limit exceeded"),
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.context.get('user')

        # Always return 200 — no email enumeration
        if user is None:
            return Response(
                {"message": "If an account exists with that email, a reset code has been sent."},
                status=status.HTTP_200_OK,
            )

        code = EmailVerification.generate_code()
        EmailVerification.objects.create(
            user=user,
            code=code,
            purpose=EmailVerification.Purpose.PASSWORD_RESET,
        )

        try:
            send_email(user, code, template_key='password_reset')
        except Exception:
            pass  # Non-fatal — log already captured inside send_email

        return Response(
            {"message": "If an account exists with that email, a reset code has been sent."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Password Reset — Confirm
# ---------------------------------------------------------------------------

class PasswordResetConfirmView(GenericAPIView):
    serializer_class = PasswordResetConfirmSerializer

    @extend_schema(
        request=PasswordResetConfirmSerializer,
        responses={
            200: OpenApiResponse(description="Password reset successful"),
            400: OpenApiResponse(description="Invalid code or passwords do not match"),
        }
    )
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            {"message": "Password reset successful. Please log in with your new password."},
            status=status.HTTP_200_OK,
        )


# ---------------------------------------------------------------------------
# Countries
# ---------------------------------------------------------------------------

class CountryListCreateView(ListCreateAPIView):
    """
    get:
    Return a list of all existing countries.

    post:
    Create a new country instance.
    """
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    # permission_classes = [IsAuthenticated]

class CountryDetailView(RetrieveUpdateDestroyAPIView):
    """
    get:
    Return the given country.

    put:
    Update the given country.

    patch:
    Partially update the given country.

    delete:
    Delete the given country.
    """
    queryset = Country.objects.all()
    serializer_class = CountrySerializer
    # permission_classes = [IsAuthenticated]