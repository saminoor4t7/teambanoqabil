import secrets
import smtplib
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError

from .models import AuditLog, PendingRegistration
from .serializers import LoginSerializer, RegistrationOTPVerifySerializer, RegisterSerializer, UserSerializer

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
                role=data["role"],
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

        try:
            message = EmailMultiAlternatives(
                subject="Your Medical Panda verification code",
                body=(
                    f"Your Medical Panda verification code is {pending.otp_code}.\n\n"
                    "This code expires in 5 minutes. If you didn't request it, you can "
                    "safely ignore this email."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[pending.email],
            )
            message.attach_alternative(
                f"""\
<!doctype html>
<html lang="en">
  <body style="margin:0;padding:0;background:#f3f7f6;font-family:Arial,Helvetica,sans-serif;color:#18332f;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f7f6;padding:36px 16px;">
      <tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:520px;background:#ffffff;border-radius:16px;overflow:hidden;">
          <tr><td style="background:#087f6b;padding:26px 32px;color:#ffffff;">
            <div style="font-size:13px;font-weight:bold;letter-spacing:1.5px;text-transform:uppercase;">Medical Panda</div>
            <div style="font-size:25px;font-weight:bold;margin-top:12px;">Verify your email</div>
          </td></tr>
          <tr><td style="padding:32px;">
            <p style="font-size:16px;line-height:1.6;margin:0 0 20px;">Use this one-time code to finish creating your account:</p>
            <div style="background:#eef8f5;border:1px solid #d5eee6;border-radius:12px;padding:18px;text-align:center;font-size:34px;font-weight:bold;letter-spacing:9px;color:#087f6b;">
              {pending.otp_code}
            </div>
            <p style="font-size:14px;line-height:1.6;color:#526660;margin:20px 0 0;">This code expires in <strong>5 minutes</strong>. For your security, don't share it with anyone.</p>
            <p style="font-size:13px;line-height:1.6;color:#71827d;margin:20px 0 0;">If you didn't request this code, you can safely ignore this email.</p>
          </td></tr>
          <tr><td style="padding:18px 32px;background:#f8fbfa;color:#82918c;font-size:12px;">Medical Panda · Account verification</td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""",
                "text/html",
            )
            message.send(fail_silently=False)
        except (OSError, smtplib.SMTPException):
            pending.delete()
            return Response(
                {"detail": "Could not send the registration code. Check email configuration and try again."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response(
            {"detail": "Registration code sent to your email address.", "email": pending.email},
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        return Response(
            {
                "access": serializer.validated_data["access"],
                "refresh": serializer.validated_data["refresh"],
                "user": UserSerializer(user).data,
            }
        )


class LogoutView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response({"detail": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh_token).blacklist()
        except TokenError:
            return Response({"detail": "Invalid or expired refresh token."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Logout successful."}, status=status.HTTP_205_RESET_CONTENT)


class RegistrationOTPVerifyView(APIView):
    """Create the User only after a valid registration OTP is submitted."""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegistrationOTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            pending = PendingRegistration.objects.select_for_update().filter(
                email__iexact=data["email"], role=data["role"]
            ).first()
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
