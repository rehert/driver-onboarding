# ============================================================
# 1. IMPORTS
# ============================================================

from django import forms
from django.contrib import admin, messages
from .email_service import send_project_email
from django.utils import timezone
from django.utils.html import format_html

from .models import DriverApplication


# ============================================================
# 2. ADMIN VALIDATION FORM
# Controls how management is allowed to change status.
# ============================================================

class DriverApplicationAdminForm(forms.ModelForm):

    class Meta:
        model = DriverApplication
        fields = "__all__"

    def clean(self):

        cleaned_data = super().clean()

        new_status = cleaned_data.get(
            "status"
        )

        rejection_reason = (
            cleaned_data.get(
                "rejection_reason",
                "",
            )
            or ""
        ).strip()

        # ----------------------------------------------------
        # Rejecting requires a reason
        # ----------------------------------------------------

        if (
            new_status == "Rejected"
            and not rejection_reason
        ):

            self.add_error(
                "rejection_reason",
                "A rejection reason is required.",
            )

        # ----------------------------------------------------
        # Protect application status transitions
        # ----------------------------------------------------

        if self.instance.pk:

            old_application = (
                DriverApplication.objects.get(
                    pk=self.instance.pk
                )
            )

            old_status = old_application.status

            # A Draft must be submitted by the driver,
            # not manually converted by management.
            if (
                old_status == "Draft"
                and new_status != "Draft"
            ):

                self.add_error(
                    "status",
                    (
                        "A Draft application must be "
                        "submitted by the driver."
                    ),
                )

            # Once a final decision has been made,
            # do not silently change it again.
            if (
                old_status in [
                    "Approved",
                    "Rejected",
                ]
                and new_status != old_status
            ):

                self.add_error(
                    "status",
                    (
                        "A completed management decision "
                        "cannot be changed here."
                    ),
                )

        return cleaned_data


# ============================================================
# 3. DRIVER APPLICATION ADMIN
# ============================================================

@admin.register(DriverApplication)
class DriverApplicationAdmin(admin.ModelAdmin):

    form = DriverApplicationAdminForm

    # ========================================================
    # 4. ADMIN LIST PAGE
    # ========================================================

    list_display = [
        "full_name",
        "transport",
        "status",
        "user_email",
        "submitted_at",
        "notification_sent",
    ]

    list_filter = [
        "status",
        "transport",
        "notification_sent",
    ]

    search_fields = [
        "full_name",
        "user__email",
        "registration_plate",
    ]

    ordering = [
        "-created_at",
    ]

    # ========================================================
    # 5. DRIVER DATA IS READ-ONLY FOR MANAGEMENT
    # Management reviews it but should not rewrite it.
    # ========================================================

    readonly_fields = [
        "user",
        "transport",

        "full_name",
        "date_of_birth",
        "contact_info",
        "country_of_origin",
        "city",
        "licence_class",

        "id_photo_link",
        "licence_photo_link",

        "registration_plate",
        "vehicle_make",
        "vehicle_model",
        "vehicle_year",
        "vehicle_colour",
        "country_of_operation",
        "city_of_work",

        "front_vehicle_photo_link",
        "rear_vehicle_photo_link",
        "cargo_area_photo_link",
        "vehicle_registration_document_link",
        "applicant_portrait_link",

        "terms_accepted",
        "current_step",

        "submitted_at",
        "decision_at",

        "notification_sent",
        "notification_error",

        "created_at",
        "updated_at",
    ]

    # ========================================================
    # 6. ORGANISE ADMIN PAGE
    # ========================================================

    fieldsets = [

        (
            "Application",
            {
                "fields": [
                    "user",
                    "status",
                    "transport",
                    "current_step",
                ]
            },
        ),

        (
            "Personal details",
            {
                "fields": [
                    "full_name",
                    "date_of_birth",
                    "contact_info",
                    "country_of_origin",
                    "city",
                    "licence_class",
                    "id_photo_link",
                    "licence_photo_link",
                ]
            },
        ),

        (
            "Vehicle details",
            {
                "fields": [
                    "registration_plate",
                    "vehicle_make",
                    "vehicle_model",
                    "vehicle_year",
                    "vehicle_colour",
                    "country_of_operation",
                    "city_of_work",
                ]
            },
        ),

        (
            "Photos and documents",
            {
                "fields": [
                    "front_vehicle_photo_link",
                    "rear_vehicle_photo_link",
                    "cargo_area_photo_link",
                    "vehicle_registration_document_link",
                    "applicant_portrait_link",
                ]
            },
        ),

        (
            "Management decision",
            {
                "fields": [
                    "rejection_reason",
                    "decision_at",
                ]
            },
        ),

        (
            "Notification",
            {
                "fields": [
                    "notification_sent",
                    "notification_error",
                ]
            },
        ),

        (
            "System information",
            {
                "fields": [
                    "terms_accepted",
                    "submitted_at",
                    "created_at",
                    "updated_at",
                ]
            },
        ),
    ]

    # ========================================================
    # 7. RETRY EMAIL ADMIN ACTION
    # ========================================================

    actions = [
        "retry_decision_notification",
    ]

    # ========================================================
    # 8. DISPLAY USER EMAIL
    # ========================================================

    @admin.display(
        description="Email"
    )
    def user_email(
        self,
        obj,
    ):
        return obj.user.email

    # ========================================================
    # 9. DOCUMENT LINKS
    # ========================================================

    def file_link(
        self,
        file_field,
    ):

        if not file_field:
            return "No file"

        return format_html(
            '<a href="{}" target="_blank">'
            'Open file'
            '</a>',
            file_field.url,
        )

    @admin.display(
        description="ID photo"
    )
    def id_photo_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.id_photo
        )

    @admin.display(
        description="Licence photo"
    )
    def licence_photo_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.licence_photo
        )

    @admin.display(
        description="Front vehicle photo"
    )
    def front_vehicle_photo_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.front_vehicle_photo
        )

    @admin.display(
        description="Rear vehicle photo"
    )
    def rear_vehicle_photo_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.rear_vehicle_photo
        )

    @admin.display(
        description="Cargo-area photo"
    )
    def cargo_area_photo_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.cargo_area_photo
        )

    @admin.display(
        description="Vehicle registration document"
    )
    def vehicle_registration_document_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.vehicle_registration_document
        )

    @admin.display(
        description="Applicant portrait"
    )
    def applicant_portrait_link(
        self,
        obj,
    ):
        return self.file_link(
            obj.applicant_portrait
        )

    # ========================================================
    # 10. SEND MANAGEMENT DECISION EMAIL
    # ========================================================

    def send_decision_notification(
        self,
        application,
    ):

        # Only final decisions have notification emails.
        if application.status not in [
            "Approved",
            "Rejected",
        ]:
            return False

        if application.status == "Approved":

            subject = (
                "Driver Application Approved"
            )

            message = (
                f"Hello {application.full_name},\n\n"
                "Your driver application has been "
                "approved.\n\n"
                "Thank you."
            )

        else:

            subject = (
                "Driver Application Rejected"
            )

            message = (
                f"Hello {application.full_name},\n\n"
                "Your driver application has been "
                "rejected.\n\n"
                f"Reason: "
                f"{application.rejection_reason}\n\n"
                "Thank you."
            )

        try:

            send_project_email(
                subject=subject,
                message=message,
                recipient=application.user.email,
            )

        except Exception as error:

            # IMPORTANT:
            # The management decision was already saved.
            # Only the notification is marked as failed.
            DriverApplication.objects.filter(
                pk=application.pk
            ).update(
                notification_sent=False,
                notification_error=str(error),
            )

            return False

        else:

            DriverApplication.objects.filter(
                pk=application.pk
            ).update(
                notification_sent=True,
                notification_error="",
            )

            return True

    # ========================================================
    # 11. SAVE MANAGEMENT DECISION FIRST,
    # THEN ATTEMPT EMAIL
    # ========================================================

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):

        old_status = None

        if obj.pk:

            old_status = (
                DriverApplication.objects
                .get(pk=obj.pk)
                .status
            )

        decision_changed = (
            old_status == "Submitted"
            and obj.status in [
                "Approved",
                "Rejected",
            ]
        )

        if decision_changed:

            obj.decision_at = timezone.now()

            # Reset notification state before attempting it
            obj.notification_sent = False
            obj.notification_error = ""

        # ----------------------------------------------------
        # SAVE DECISION TO DATABASE FIRST
        # ----------------------------------------------------

        super().save_model(
            request,
            obj,
            form,
            change,
        )

        # ----------------------------------------------------
        # THEN ATTEMPT EMAIL
        # ----------------------------------------------------

        if decision_changed:

            success = (
                self.send_decision_notification(
                    obj
                )
            )

            if success:

                self.message_user(
                    request,
                    "Decision saved and email sent.",
                    level=messages.SUCCESS,
                )

            else:

                self.message_user(
                    request,
                    (
                        "Decision was saved, but the "
                        "notification email failed. "
                        "You can retry it from the "
                        "application list."
                    ),
                    level=messages.WARNING,
                )

    # ========================================================
    # 12. RETRY FAILED NOTIFICATION
    # ========================================================

    @admin.action(
        description=
        "Retry decision notification email"
    )
    def retry_decision_notification(
        self,
        request,
        queryset,
    ):

        success_count = 0
        failure_count = 0

        for application in queryset:

            if application.status not in [
                "Approved",
                "Rejected",
            ]:
                continue

            if self.send_decision_notification(
                application
            ):
                success_count += 1

            else:
                failure_count += 1

        if success_count:

            self.message_user(
                request,
                (
                    f"{success_count} notification(s) "
                    "sent successfully."
                ),
                level=messages.SUCCESS,
            )

        if failure_count:

            self.message_user(
                request,
                (
                    f"{failure_count} notification(s) "
                    "failed."
                ),
                level=messages.WARNING,
            )