import secrets
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken

from .models import AuditLog, PendingRegistration
from .serializers import RegistrationOTPVerifySerializer, RegisterSerializer, UserSerializer

User = get_user_model()


def token_response(user):
    refresh = RefreshToken.for_user(user)
    return Response(
        {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user).data,
        }
    )


class RegisterView(generics.CreateAPIView):
    """Store a temporary registration and email its verification code."""

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        otp_code = f"{secrets.randbelow(1_000_000):06d}"

        try:
            pending, _ = PendingRegistration.objects.update_or_create(
                email=data["email"],
                defaults={
                    "username": data["username"],
                    "password_hash": make_password(data["password"]),
                    "role": data["role"],
                    "phone_number": data["phone_number"],
                    "first_name": data.get("first_name", ""),
                    "last_name": data.get("last_name", ""),
                    "otp_code": otp_code,
                    "expires_at": timezone.now() + timedelta(minutes=5),
                },
            )
        except IntegrityError:
            return Response(
                {"detail": "Username or phone number is already pending verification."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_mail(
            subject="Medical Panda registration code",
            message=(
                f"Your Medical Panda verification code is: {pending.otp_code}\n\n"
                "This code expires in 5 minutes."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[pending.email],
            fail_silently=False,
        )
        return Response(
            {"detail": "Registration code sent to your email address.", "email": pending.email},
            status=status.HTTP_201_CREATED,
        )


class RegistrationOTPVerifyView(APIView):
    """Create the User only after a valid registration OTP is submitted."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegistrationOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            pending = PendingRegistration.objects.select_for_update().filter(email__iexact=data["email"]).first()
            if not pending:
                return Response({"detail": "No pending registration with this email address."}, status=status.HTTP_404_NOT_FOUND)
            if pending.otp_code != data["code"] or pending.expires_at < timezone.now():
                return Response({"detail": "Invalid or expired OTP."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                user = User.objects.create(
                    username=pending.username,
                    email=pending.email,
                    password=pending.password_hash,
                    role=pending.role,
                    phone_number=pending.phone_number,
                    first_name=pending.first_name,
                    last_name=pending.last_name,
                )
            except IntegrityError:
                return Response(
                    {"detail": "An account with these registration details already exists."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            pending.delete()
            AuditLog.objects.create(actor=user, action="user_registered", target_type="User", target_id=str(user.id))

        return token_response(user)
