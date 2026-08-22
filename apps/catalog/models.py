from django.db import models


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Brand(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Medicine(models.Model):
    """The verified catalog that AI medicine-matching (FR-06) resolves
    extracted prescription text against — pharmacies never sell items
    outside this catalog."""

    name = models.CharField(max_length=200)
    generic_name = models.CharField(max_length=200, blank=True)
    strength = models.CharField(max_length=50, blank=True)  # e.g. "500mg"
    form = models.CharField(max_length=50, blank=True)  # tablet/syrup/injection
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL, related_name="medicines")
    brand = models.ForeignKey(Brand, null=True, blank=True, on_delete=models.SET_NULL, related_name="medicines")
    requires_prescription = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to="medicines/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["name"])]

    def __str__(self):
        return f"{self.name} {self.strength}".strip()
