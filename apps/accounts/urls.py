from django.urls import path

from .views import RegisterView, RegistrationOTPVerifyView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("register/verify/", RegistrationOTPVerifyView.as_view(), name="register-verify"),
]
