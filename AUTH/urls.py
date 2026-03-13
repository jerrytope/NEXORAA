from django.urls import path
from .views import (
    RegisterView,
    EmailVerificationView,
    LoginView,
    LogoutView,
    ResendVerificationView,
    TokenRefreshViewCustom,
    TokenObtainPairViewCustom,
    MeView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    CountryListCreateView,
    CountryDetailView,
)

urlpatterns = [
    # --- Registration & Verification ---
    path('register/', RegisterView.as_view(), name='register'),
    path('verify-email/', EmailVerificationView.as_view(), name='verify-email'),
    path('resend-verification/', ResendVerificationView.as_view(), name='resend-verification'),

    # --- Auth ---
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),

    # --- JWT Tokens ---
    path('token/', TokenObtainPairViewCustom.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshViewCustom.as_view(), name='token_refresh'),

    # --- Password Reset ---
    path('password-reset/request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm'),

    # --- Current User ---
    path('me/', MeView.as_view(), name='me'),

    # --- Countries ---
    path('countries/', CountryListCreateView.as_view(), name='country-list'),
    path('countries/<int:pk>/', CountryDetailView.as_view(), name='country-detail'),
]