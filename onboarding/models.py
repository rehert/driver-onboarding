# ============================================================
# 1. IMPORTS
# ============================================================

from django.contrib.auth.models import User
from django.db import models


# ============================================================
# 2. DRIVER APPLICATION MODEL
# One record represents one driver's application.
# ============================================================

class DriverApplication(models.Model):

    # ========================================================
    # 3. APPLICATION STATUS OPTIONS
    # ========================================================

    STATUS_CHOICES = [
        ("Draft", "Draft"),
        ("Submitted", "Submitted"),
        ("Approved", "Approved"),
        ("Rejected", "Rejected"),
    ]

    # ========================================================
    # 4. ACCOUNT AND STEP 1
    # ========================================================

    # One user can only have one driver application.
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
    )

    transport = models.CharField(
        max_length=20,
    )

    # ========================================================
    # 5. STEP 2 — PERSONAL DETAILS
    # ========================================================

    full_name = models.CharField(
        max_length=150,
    )

    date_of_birth = models.DateField()

    contact_info = models.CharField(
        max_length=100,
    )

    country_of_origin = models.CharField(
        max_length=100,
    )

    # This stores the applicant's city of birth.
    city = models.CharField(
        max_length=100,
    )

    id_photo = models.ImageField(
        upload_to="id_photos/",
    )

    licence_photo = models.ImageField(
        upload_to="licence_photos/",
    )

    licence_class = models.CharField(
        max_length=20,
    )

    # ========================================================
    # 6. STEP 3 — VEHICLE DETAILS
    # blank=True because these are added after Step 2.
    # ========================================================

    registration_plate = models.CharField(
        max_length=30,
        blank=True,
    )

    vehicle_make = models.CharField(
        max_length=50,
        blank=True,
    )

    vehicle_model = models.CharField(
        max_length=50,
        blank=True,
    )

    vehicle_year = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    vehicle_colour = models.CharField(
        max_length=30,
        blank=True,
    )

    country_of_operation = models.CharField(
        max_length=100,
        blank=True,
    )

    city_of_work = models.CharField(
        max_length=100,
        blank=True,
    )

    # ========================================================
    # 7. STEP 4 — PHOTOS AND DOCUMENTS
    # ========================================================

    front_vehicle_photo = models.ImageField(
        upload_to="vehicle_photos/",
        blank=True,
    )

    rear_vehicle_photo = models.ImageField(
        upload_to="vehicle_photos/",
        blank=True,
    )

    cargo_area_photo = models.ImageField(
        upload_to="vehicle_photos/",
        blank=True,
    )

    vehicle_registration_document = models.ImageField(
        upload_to="vehicle_documents/",
        blank=True,
    )

    applicant_portrait = models.ImageField(
        upload_to="portraits/",
        blank=True,
    )

    # ========================================================
    # 8. STEP 5 — SUBMISSION
    # ========================================================

    terms_accepted = models.BooleanField(
        default=False,
    )

    submitted_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # ========================================================
    # 9. APPLICATION PROGRESS
    # ========================================================

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="Draft",
    )

    # Used to resume a Draft application later.
    current_step = models.PositiveIntegerField(
        default=2,
    )

    # ========================================================
    # 10. MANAGEMENT DECISION
    # ========================================================

    rejection_reason = models.TextField(
        blank=True,
    )

    decision_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    # Did the approval/rejection email successfully send?
    notification_sent = models.BooleanField(
        default=False,
    )

    # If email sending fails, save the error here.
    notification_error = models.TextField(
        blank=True,
    )

    # ========================================================
    # 11. AUTOMATIC TIMESTAMPS
    # ========================================================

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    # ========================================================
    # 12. HUMAN-READABLE NAME
    # ========================================================

    def __str__(self):
        return (
            f"{self.full_name} "
            f"- {self.status}"
        )