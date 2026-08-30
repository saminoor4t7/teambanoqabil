from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import PendingRegistration, Role

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "phone_number", "phone_verified", "date_joined"]
        read_only_fields = ["id", "phone_verified", "date_joined"]


class LoginSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(write_only=True)
    role = serializers.ChoiceField(choices=Role.choices, write_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.pop(User.USERNAME_FIELD, None)

    def validate(self, attrs):
        email = attrs["email"].strip().lower()
        role = attrs["role"]
        user = next(
            (
                candidate
                for candidate in User.objects.filter(email__iexact=email, role=role, is_active=True)
                if candidate.check_password(attrs["password"])
            ),
            None,
        )
        if not user:
            raise AuthenticationFailed(
                self.error_messages["no_active_account"],
                "no_active_account",
            )

        refresh = self.get_token(user)
        return {
            "refresh": str(refresh),
            "access": str(refresh.access_token),
            "user": user,
        }


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, validators=[validate_password])
    role = serializers.ChoiceField(choices=Role.choices)
    phone_number = serializers.CharField(max_length=20)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_email(self, value):
        email = value.strip().lower()
        return email

    def validate_username(self, value):
        return value

    def validate(self, attrs):
        role = attrs["role"]
        username = attrs["username"]
        email = attrs["email"]
        phone_number = attrs["phone_number"]

        if User.objects.filter(username=username, role=role).exists():
            raise serializers.ValidationError({"username": "A user with this username already exists for this role."})
        if User.objects.filter(email__iexact=email, role=role).exists():
            raise serializers.ValidationError({"email": "An account with this email already exists for this role."})
        if User.objects.filter(phone_number=phone_number, role=role).exists():
            raise serializers.ValidationError({"phone_number": "An account with this phone number already exists for this role."})

        pending = PendingRegistration.objects.filter(email__iexact=email, role=role).first()
        if PendingRegistration.objects.filter(username=username, role=role).exclude(
            pk=pending.pk if pending else None
        ).exists():
            raise serializers.ValidationError({"username": "This username already has a pending registration for this role."})
        if pending and pending.username != attrs["username"]:
            raise serializers.ValidationError({"username": "This email already has a pending registration for this role."})
        if PendingRegistration.objects.filter(phone_number=phone_number, role=role).exclude(
            pk=pending.pk if pending else None
        ).exists():
            raise serializers.ValidationError({"phone_number": "This phone number already has a pending registration for this role."})
        return attrs


class RegistrationOTPVerifySerializer(serializers.Serializer):
    email = serializers.EmailField()
    role = serializers.ChoiceField(choices=Role.choices)
    code = serializers.CharField(max_length=6)
