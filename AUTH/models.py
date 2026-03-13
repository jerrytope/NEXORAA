import random
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class Country(models.Model):
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=2, unique=True)  # ISO alpha-2
    phone_code = models.CharField(max_length=10, blank=True, null=True)
    flag_emoji = models.CharField(max_length=10, blank=True, null=True)
    currency_code = models.CharField(max_length=10, blank=True, null=True)
    currency_symbol = models.CharField(max_length=5, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "Countries"
        ordering = ['name']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['is_active']),
        ]

    def __str__(self):
        return f"{self.name} ({self.code})"


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('Email must be provided')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_verified', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):

    class Role(models.TextChoices):
        CREATOR = 'creator', 'Creator'
        BRAND = 'brand', 'Brand'
        ADMIN = 'admin', 'Admin'

    # --- Core auth fields ---
    email = models.EmailField(unique=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)  # False until email verified
    is_staff = models.BooleanField(default=False)

    # --- Name fields ---
    first_name = models.CharField(max_length=50, blank=True)
    last_name = models.CharField(max_length=50, blank=True)

    # --- Role ---
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        null=False,
        blank=False,
        default=Role.CREATOR,
    )

    # --- Shared profile fields ---
    contact_person = models.CharField(max_length=150, blank=True, null=True)
    contact_person_number = models.CharField(max_length=30, blank=True, null=True)

    # --- Brand-specific fields ---
    brand_name = models.CharField(max_length=150, blank=True, null=True)

    # --- Location ---
    country = models.ForeignKey(
        Country,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
    )

    # --- Referral ---
    referral_code = models.CharField(max_length=100, blank=True, null=True)

    # --- Terms ---
    agree_to_terms = models.BooleanField(default=True)

    # --- Timestamps ---
    date_joined = models.DateTimeField(default=timezone.now)

    objects = CustomUserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    class Meta:
        indexes = [
            models.Index(fields=['role']),
            models.Index(fields=['is_active', 'is_verified']),
        ]

    def __str__(self):
        return f"{self.email} ({self.role})"

    @property
    def full_name(self):
        if self.first_name or self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.contact_person or self.email


class EmailVerification(models.Model):

    class Purpose(models.TextChoices):
        EMAIL_VERIFICATION = 'email_verification', 'Email Verification'
        PASSWORD_RESET = 'password_reset', 'Password Reset'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verifications'
    )
    code = models.CharField(max_length=6, db_index=True)
    purpose = models.CharField(
        max_length=20,
        choices=Purpose.choices,
        default=Purpose.EMAIL_VERIFICATION,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['user', 'is_used']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['purpose']),
        ]

    def save(self, *args, **kwargs):
        if not self.pk:
            self.expires_at = timezone.now() + timedelta(minutes=5)
        super().save(*args, **kwargs)

    @staticmethod
    def generate_code():
        return str(random.randint(100000, 999999))

    def mark_used(self):
        self.is_used = True
        self.save(update_fields=['is_used'])

    def is_expired(self):
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"{self.user.email} — {self.purpose} — {'used' if self.is_used else 'active'}"