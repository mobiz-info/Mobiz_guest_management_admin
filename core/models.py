from django.db import models
import uuid


# ============================================================
# COUNTRY MASTER
# ============================================================

class Country(models.Model):
    name = models.CharField(max_length=100, unique=True)
    currency_code = models.CharField(max_length=10, blank=True, null=True)
    emblem = models.CharField(max_length=10, blank=True, null=True)
    dial_code = models.CharField(max_length=10, blank=True, null=True)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Country"
        verbose_name_plural = "Countries"

    def __str__(self):
        return self.name


# ============================================================
# STATE / PROVINCE MASTER
# ============================================================

class State(models.Model):
    country = models.ForeignKey(
        Country,
        on_delete=models.CASCADE,
        related_name='states'
    )
    name = models.CharField(max_length=100)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "State / Province"
        verbose_name_plural = "States / Provinces"

        constraints = [
            models.UniqueConstraint(
                fields=['country', 'name'],
                name='unique_state_country'
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.country.name}"


# ============================================================
# DISTRICT MASTER
# ============================================================

class District(models.Model):
    state = models.ForeignKey(
        State,
        on_delete=models.CASCADE,
        related_name='districts'
    )
    name = models.CharField(max_length=100)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "District"
        verbose_name_plural = "Districts"

        constraints = [
            models.UniqueConstraint(
                fields=['state', 'name'],
                name='unique_district_state'
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.state.name}"


# ============================================================
# AREA MASTER
# ============================================================

class Area(models.Model):
    district = models.ForeignKey(
        District,
        on_delete=models.CASCADE,
        related_name='areas'
    )
    name = models.CharField(max_length=100)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Area"
        verbose_name_plural = "Areas"

        constraints = [
            models.UniqueConstraint(
                fields=['district', 'name'],
                name='unique_area_district'
            )
        ]

    def __str__(self):
        return f"{self.name} - {self.district.name}"


# ============================================================
# DESIGNATION MASTER
# ============================================================

class Designation(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(max_length=100, unique=True)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Designation"
        verbose_name_plural = "Designations"

    def __str__(self):
        return self.name


# ============================================================
# ESTABLISHMENT TYPE MASTER
# ============================================================

class EstablishmentType(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(max_length=100, unique=True)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Establishment Type"
        verbose_name_plural = "Establishment Types"

    def __str__(self):
        return self.name


# ============================================================
# PURPOSE OF VISIT MASTER
# ============================================================

class PurposeOfVisit(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )
    name = models.CharField(max_length=150, unique=True)
    status = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = "Purpose of Visit"
        verbose_name_plural = "Purposes of Visit"

    def __str__(self):
        return self.name
