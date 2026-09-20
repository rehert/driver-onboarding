# ============================================================
# 1. IMPORTS
# ============================================================

import secrets
import time
from datetime import datetime
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password

from django.core.exceptions import ValidationError
from django.conf import settings
from django.http import FileResponse, Http404
from django.core.mail import send_mail

from django.db import transaction

from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)

from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import DriverApplication


# ============================================================
# 2. CONSTANTS
# Numbers that control OTP and file-upload behaviour
# ============================================================

OTP_EXPIRY_SECONDS = 120
OTP_RESEND_COOLDOWN = 30

# Maximum incorrect OTP attempts
OTP_MAX_ATTEMPTS = 3

# Maximum OTP requests allowed inside the request window
OTP_MAX_REQUESTS = 5

# 10 minutes
OTP_REQUEST_WINDOW = 600

# 5 MB expressed in bytes
MAX_FILE_SIZE = 5 * 1024 * 1024

# Minimum age allowed to apply as a driver
MIN_DRIVER_AGE = 18# Minimum age allowed to apply as a driver

ALLOWED_IMAGE_FORMATS = {"JPEG", "PNG"}
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

VALID_TRANSPORTS = {
    "motorcycle",
    "car",
    "van",
    "truck",
}


# ============================================================
# 3. GENERAL HELPER FUNCTIONS
# Small reusable functions used by several views
# ============================================================

def calculate_age(date_of_birth):
    """
    Calculate the applicant's current age.
    """

    today = timezone.localdate()

    age = today.year - date_of_birth.year

    # Subtract one if the birthday has not happened yet this year
    if (today.month, today.day) < (
        date_of_birth.month,
        date_of_birth.day,
    ):
        age -= 1

    return age


def parse_date_of_birth(date_string):
    """
    Convert the HTML date into a Python date
    and make sure the applicant is old enough.
    """

    try:
        date_of_birth = datetime.strptime(
            date_string,
            "%Y-%m-%d",
        ).date()

    except (ValueError, TypeError):
        return None, "Please enter a valid date of birth."

    # Date of birth cannot be in the future
    if date_of_birth > timezone.localdate():
        return None, "Date of birth cannot be in the future."

    # Calculate age
    age = calculate_age(date_of_birth)

    # Driver must be at least 18
    if age < MIN_DRIVER_AGE:
        return None, "You must be at least 18 years old to apply as a driver."

    return date_of_birth, None

# ============================================================
# 4. IMAGE VALIDATION
# Server-side protection for uploaded images
# ============================================================

def validate_uploaded_image(uploaded_file):
    """
    Check:
    1. File exists
    2. File <= 5 MB
    3. Filename extension is JPG/PNG
    4. Actual file contents are a real JPG/PNG image

    Returns:
        None if valid
        error message if invalid
    """

    if uploaded_file is None:
        return "Please choose an image."

    # Check file size on the server
    if uploaded_file.size > MAX_FILE_SIZE:
        return "Each image must be 5 MB or smaller."

    extension = Path(uploaded_file.name).suffix.lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "Only JPG and PNG images are allowed."

    try:
        image = Image.open(uploaded_file)

        # Do not trust only the filename extension.
        # Check the real image format.
        if image.format not in ALLOWED_IMAGE_FORMATS:
            uploaded_file.seek(0)
            return "Only valid JPG and PNG images are allowed."

        # Pillow checks whether the file is a real readable image
        image.verify()

        # Reset the file pointer because Django still needs
        # to save the file afterwards
        uploaded_file.seek(0)

    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
    ):
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        return "The selected file is not a valid image."

    return None


# ============================================================
# 5. OTP HELPER FUNCTIONS
# ============================================================

def clear_active_otp(request):
    """
    Remove the currently active OTP.

    We do NOT remove the resend timer/request history because
    those are used to prevent OTP request abuse.
    """

    request.session.pop("otp_hash", None)
    request.session.pop("otp_email", None)
    request.session.pop("otp_expires", None)
    request.session.pop("otp_attempts", None)


def otp_seconds_remaining(request):
    """
    Calculate how many seconds remain on the server OTP timer.

    Refreshing the browser does NOT restart the timer.
    """

    expiry = request.session.get("otp_expires")

    if not expiry:
        return 0

    remaining = int(expiry - time.time())

    return max(0, remaining)


def send_registration_otp(request, email):
    """
    Create and send a six-digit OTP.

    Returns:
        None = success
        string = error message
    """

    email = email.strip().lower()

    if not email:
        return "Enter an email address first."

    now = time.time()

    # --------------------------------------------------------
    # Resend cooldown
    # --------------------------------------------------------

    last_sent = request.session.get(
        "otp_last_sent",
        0,
    )

    seconds_since_last_request = now - last_sent

    if seconds_since_last_request < OTP_RESEND_COOLDOWN:

        remaining = int(
            OTP_RESEND_COOLDOWN
            - seconds_since_last_request
        )

        return (
            f"Please wait {remaining} seconds "
            f"before requesting another code."
        )

    # --------------------------------------------------------
    # Request-rate limiting
    # --------------------------------------------------------

    request_times = request.session.get(
        "otp_request_times",
        [],
    )

    # Keep only requests made during the last 10 minutes
    request_times = [
        request_time
        for request_time in request_times
        if now - request_time < OTP_REQUEST_WINDOW
    ]

    if len(request_times) >= OTP_MAX_REQUESTS:
        return (
            "Too many verification-code requests. "
            "Please wait and try again later."
        )

    # Generate a six-digit random number
    otp = str(
        secrets.randbelow(900000) + 100000
    )

    try:
        send_mail(
            subject="Driver Registration One Time Password",
            message=(
                f"Your verification code is {otp}. "
                f"It expires in {OTP_EXPIRY_SECONDS} seconds."
            ),
            from_email="rehertemmanuel@gmail.com",
            recipient_list=[email],
            using="default",
            fail_silently=False,
        )

    except Exception:
        return (
            "The verification email could not be sent. "
            "Please try again."
        )

    # Sending a new OTP means verification must happen again.
    request.session.pop(
        "verified_email",
        None,
    )

    # Save only a HASH of the OTP.
    #
    # The readable OTP is NOT stored in the session.
    from django.contrib.auth.hashers import make_password

    request.session["otp_hash"] = make_password(otp)
    request.session["otp_email"] = email

    # Server-controlled expiry
    request.session["otp_expires"] = (
        now + OTP_EXPIRY_SECONDS
    )

    request.session["otp_attempts"] = 0
    request.session["otp_last_sent"] = now

    request_times.append(now)

    request.session["otp_request_times"] = request_times

    return None


def verify_registration_otp(
    request,
    entered_otp,
    current_email,
):
    """
    Verify an OTP.

    Protects against:
    - wrong codes
    - expired codes
    - reused codes
    - too many incorrect attempts
    - changing email after OTP was requested
    """

    from django.contrib.auth.hashers import check_password

    otp_hash = request.session.get("otp_hash")
    otp_email = request.session.get("otp_email")
    otp_expiry = request.session.get("otp_expires")

    if not otp_hash or not otp_expiry:
        return "No active verification code exists."

    # The email currently displayed in the form must be the
    # same email that received the OTP.
    if current_email.strip().lower() != otp_email:
        return (
            "The email address has changed. "
            "Please request a new verification code."
        )

    # Server controls expiry
    if time.time() > otp_expiry:

        clear_active_otp(request)

        return (
            "The verification code has expired. "
            "Please request a new one."
        )

    if not entered_otp:
        return "Please enter the verification code."

    if check_password(
        entered_otp,
        otp_hash,
    ):

        request.session["verified_email"] = otp_email

        # Deleting the OTP makes it impossible to reuse
        clear_active_otp(request)

        return None

    # Incorrect OTP
    attempts = (
        request.session.get(
            "otp_attempts",
            0,
        )
        + 1
    )

    request.session["otp_attempts"] = attempts

    if attempts >= OTP_MAX_ATTEMPTS:

        clear_active_otp(request)

        return (
            "Too many incorrect attempts. "
            "Please request a new code."
        )

    attempts_left = OTP_MAX_ATTEMPTS - attempts

    return (
        f"Incorrect verification code. "
        f"{attempts_left} attempt(s) remaining."
    )


# ============================================================
# 6. FIND WHERE A DRAFT APPLICANT SHOULD RESUME
# ============================================================

def draft_resume_page(application):
    """
    Decide which page a Draft applicant should resume from.
    """

    if application.current_step <= 3:
        return "vehicle_details"

    if application.current_step == 4:
        return "documents"

    return "review_application"


# ============================================================
# 7. CHECK WHETHER THE FULL APPLICATION IS COMPLETE
# ============================================================

def find_missing_application_fields(application):
    """
    Server-side final validation before submission.

    HTML 'required' is helpful, but the server must still
    verify the application.
    """

    required_fields = {
        "Transport": application.transport,
        "Full name": application.full_name,
        "Date of birth": application.date_of_birth,
        "Phone number": application.contact_info,
        "Email": application.user.email,
        "Country of origin": application.country_of_origin,
        "City of birth": application.city,
        "ID photo": application.id_photo,
        "Licence photo": application.licence_photo,
        "Licence class": application.licence_class,

        "Registration plate": application.registration_plate,
        "Vehicle make": application.vehicle_make,
        "Vehicle model": application.vehicle_model,
        "Vehicle year": application.vehicle_year,
        "Vehicle colour": application.vehicle_colour,
        "Country of operation": application.country_of_operation,
        "City of work": application.city_of_work,

        "Front vehicle photo": application.front_vehicle_photo,
        "Rear vehicle photo": application.rear_vehicle_photo,
        "Cargo-area photo": application.cargo_area_photo,
        "Vehicle registration document":
            application.vehicle_registration_document,
        "Applicant portrait": application.applicant_portrait,
    }

    missing = []

    for field_name, value in required_fields.items():
        if not value:
            missing.append(field_name)

    return missing



# ============================================================
# PROTECTED UPLOADED FILES
# Drivers may open only their own files. Staff may review all.
# ============================================================

@login_required(login_url="sign_in")
def protected_media(request, file_path):
    media_root = Path(settings.MEDIA_ROOT).resolve()
    requested_file = (media_root / file_path).resolve()

    try:
        requested_file.relative_to(media_root)
    except ValueError:
        raise Http404("File not found.")

    if not requested_file.is_file():
        raise Http404("File not found.")

    if not request.user.is_staff:
        application = DriverApplication.objects.filter(user=request.user).first()
        if application is None:
            raise Http404("File not found.")

        allowed_names = {
            getattr(application, field).name
            for field in (
                "id_photo",
                "licence_photo",
                "front_vehicle_photo",
                "rear_vehicle_photo",
                "cargo_area_photo",
                "vehicle_registration_document",
                "applicant_portrait",
            )
            if getattr(application, field)
        }
        if file_path not in allowed_names:
            raise Http404("File not found.")

    return FileResponse(open(requested_file, "rb"))

# ============================================================
# 8. HOME PAGE
# ============================================================

def home(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    return render(
        request,
        "onboarding/home.html",
    )


# ============================================================
# 9. STEP 1 — CHOOSE TRANSPORT
# ============================================================

def choose_transport(request):

    selected_transport = request.session.get(
        "transport",
        "",
    )

    # --------------------------------------------------------
    # Applicant already has an account
    # Used when editing the application later
    # --------------------------------------------------------

    if request.user.is_authenticated:

        application = get_object_or_404(
            DriverApplication,
            user=request.user,
        )

        if application.status != "Draft":
            return redirect("dashboard")

        selected_transport = application.transport

        if request.method == "POST":

            transport = request.POST.get(
                "transport",
            )

            if transport not in VALID_TRANSPORTS:

                messages.error(
                    request,
                    "Please choose a valid transport type.",
                )

            else:

                application.transport = transport
                application.save(
                    update_fields=[
                        "transport",
                        "updated_at",
                    ]
                )

                messages.success(
                    request,
                    "Transport updated.",
                )

                if application.current_step >= 5:
                    return redirect(
                        "review_application"
                    )

                return redirect(
                    "vehicle_details"
                )

    # --------------------------------------------------------
    # Applicant has not created account yet
    # --------------------------------------------------------

    elif request.method == "POST":

        transport = request.POST.get(
            "transport",
        )

        if transport not in VALID_TRANSPORTS:

            messages.error(
                request,
                "Please choose a transport type.",
            )

        else:

            # Temporarily stored in session until Step 2
            request.session["transport"] = transport

            return redirect(
                "personal_details"
            )

    return render(
        request,
        "onboarding/choose_transport.html",
        {
            "selected_transport":
                selected_transport,
        },
    )


# ============================================================
# 10. STEP 2 — PERSONAL DETAILS + EMAIL VERIFICATION
# ============================================================

def personal_details(request):

    # An authenticated driver already completed registration.
    if request.user.is_authenticated:

        return redirect(
            "edit_personal_details"
        )

    transport = request.session.get(
        "transport"
    )

    if transport not in VALID_TRANSPORTS:

        messages.error(
            request,
            "Please choose your transport first.",
        )

        return redirect(
            "choose_transport"
        )

    if request.method == "POST":

        action = request.POST.get(
            "action"
        )

        email = (
            request.POST.get(
                "Email",
                "",
            )
            .strip()
            .lower()
        )

        # ----------------------------------------------------
        # SEND OTP
        # ----------------------------------------------------

        if action == "send_otp":

            error = send_registration_otp(
                request,
                email,
            )

            if error:
                messages.error(
                    request,
                    error,
                )

            else:
                messages.success(
                    request,
                    "Verification code sent. "
                    "Check your email.",
                )

        # ----------------------------------------------------
        # VERIFY OTP
        # ----------------------------------------------------

        elif action == "verify_otp":

            entered_otp = request.POST.get(
                "otp",
                "",
            )

            error = verify_registration_otp(
                request,
                entered_otp,
                email,
            )

            if error:
                messages.error(
                    request,
                    error,
                )

            else:
                messages.success(
                    request,
                    "Email successfully verified.",
                )

        # ----------------------------------------------------
        # COMPLETE STEP 2
        # ----------------------------------------------------

        elif action == "complete_step2":

            full_name = request.POST.get(
                "Full_name",
                "",
            ).strip()

            phone_number = request.POST.get(
                "Phone_number",
                "",
            ).strip()

            date_string = request.POST.get(
                "Date_of_Birth",
                "",
            )

            country = request.POST.get(
                "Country",
                "",
            ).strip()

            city = request.POST.get(
                "City",
                "",
            ).strip()

            licence_class = request.POST.get(
                "license_class",
                "",
            )

            password = request.POST.get(
                "password",
                "",
            )

            confirm_password = request.POST.get(
                "confirm password",
                "",
            )

            id_photo = request.FILES.get(
                "id_number"
            )

            licence_photo = request.FILES.get(
                "license_photo"
            )

            verified_email = request.session.get(
                "verified_email"
            )

            # ------------------------------------------------
            # Required-field validation
            # ------------------------------------------------

            if not all([
                full_name,
                phone_number,
                date_string,
                email,
                country,
                city,
                licence_class,
                password,
                confirm_password,
                id_photo,
                licence_photo,
            ]):

                messages.error(
                    request,
                    "Please complete all required fields.",
                )

            elif email != verified_email:

                messages.error(
                    request,
                    "Please verify this email address "
                    "before continuing.",
                )

            elif password != confirm_password:

                messages.error(
                    request,
                    "Passwords do not match.",
                )

            elif User.objects.filter(
                username=email
            ).exists():

                messages.error(
                    request,
                    "An account with this email "
                    "already exists.",
                )

            else:

                # --------------------------------------------
                # Validate date of birth
                # --------------------------------------------

                date_of_birth, date_error = (
                    parse_date_of_birth(
                        date_string
                    )
                )

                if date_error:

                    messages.error(
                        request,
                        date_error,
                    )

                else:

                    # ----------------------------------------
                    # Validate uploaded ID image
                    # ----------------------------------------

                    id_error = (
                        validate_uploaded_image(
                            id_photo
                        )
                    )

                    licence_error = (
                        validate_uploaded_image(
                            licence_photo
                        )
                    )

                    if id_error:

                        messages.error(
                            request,
                            "ID photo: "
                            + id_error,
                        )

                    elif licence_error:

                        messages.error(
                            request,
                            "Licence photo: "
                            + licence_error,
                        )

                    else:

                        # ------------------------------------
                        # Django password validation
                        # ------------------------------------

                        temporary_user = User(
                            username=email,
                            email=email,
                        )

                        try:

                            validate_password(
                                password,
                                user=temporary_user,
                            )

                        except ValidationError as error:

                            messages.error(
                                request,
                                " ".join(
                                    error.messages
                                ),
                            )

                        else:

                            # --------------------------------
                            # Create both records together
                            # --------------------------------

                            try:

                                with transaction.atomic():

                                    user = (
                                        User.objects
                                        .create_user(
                                            username=email,
                                            email=email,
                                            password=password,
                                        )
                                    )

                                    DriverApplication.objects.create(
                                        user=user,
                                        transport=transport,

                                        full_name=full_name,

                                        date_of_birth=
                                            date_of_birth,

                                        contact_info=
                                            phone_number,

                                        country_of_origin=
                                            country,

                                        city=city,

                                        id_photo=
                                            id_photo,

                                        licence_photo=
                                            licence_photo,

                                        licence_class=
                                            licence_class,

                                        status="Draft",

                                        current_step=3,
                                    )

                            except Exception:

                                messages.error(
                                    request,
                                    "The account could not "
                                    "be created. "
                                    "Please try again.",
                                )

                            else:

                                login(
                                    request,
                                    user,
                                )

                                # Registration session data
                                # is no longer required.
                                request.session.pop(
                                    "transport",
                                    None,
                                )

                                request.session.pop(
                                    "verified_email",
                                    None,
                                )

                                clear_active_otp(
                                    request
                                )

                                messages.success(
                                    request,
                                    "Account created. "
                                    "Continue with your "
                                    "vehicle details.",
                                )

                                return redirect(
                                    "vehicle_details"
                                )

    # Values are returned to the template so normal text
    # fields do not disappear after OTP requests.
    context = {

        "Full_name":
            request.POST.get(
                "Full_name",
                "",
            ),

        "Phone_number":
            request.POST.get(
                "Phone_number",
                "",
            ),

        "Date_of_Birth":
            request.POST.get(
                "Date_of_Birth",
                "",
            ),

        "Email":
            request.POST.get(
                "Email",
                "",
            ),

        "Country":
            request.POST.get(
                "Country",
                "",
            ),

        "City":
            request.POST.get(
                "City",
                "",
            ),

        "license_class":
            request.POST.get(
                "license_class",
                "",
            ),

        # Browser countdown should start from this value.
        "otp_seconds_remaining":
            otp_seconds_remaining(
                request
            ),

        "email_verified":
            bool(
                request.session.get(
                    "verified_email"
                )
            ),
    }

    return render(
        request,
        "onboarding/personal_details.html",
        context,
    )


# ============================================================
# 11. EDIT PERSONAL DETAILS
# Used from Step 5 review
# ============================================================

@login_required(
    login_url="sign_in"
)
def edit_personal_details(request):

    application = get_object_or_404(
        DriverApplication,
        user=request.user,
    )

    if application.status != "Draft":
        return redirect(
            "dashboard"
        )

    if request.method == "POST":

        action = request.POST.get(
            "action"
        )

        new_email = (
            request.POST.get(
                "Email",
                request.user.email,
            )
            .strip()
            .lower()
        )

        # ----------------------------------------------------
        # Send OTP if applicant wants to change email
        # ----------------------------------------------------

        if action == "send_otp":

            error = send_registration_otp(
                request,
                new_email,
            )

            if error:
                messages.error(
                    request,
                    error,
                )

            else:
                messages.success(
                    request,
                    "Verification code sent.",
                )

        # ----------------------------------------------------
        # Confirm OTP
        # ----------------------------------------------------

        elif action == "verify_otp":

            entered_otp = request.POST.get(
                "otp",
                "",
            )

            error = verify_registration_otp(
                request,
                entered_otp,
                new_email,
            )

            if error:
                messages.error(
                    request,
                    error,
                )

            else:
                messages.success(
                    request,
                    "Email successfully verified.",
                )

        # ----------------------------------------------------
        # Save edited personal information
        # ----------------------------------------------------

        elif action == "save_personal":

            full_name = request.POST.get(
                "Full_name",
                "",
            ).strip()

            phone_number = request.POST.get(
                "Phone_number",
                "",
            ).strip()

            date_string = request.POST.get(
                "Date_of_Birth",
                "",
            )

            country = request.POST.get(
                "Country",
                "",
            ).strip()

            city = request.POST.get(
                "City",
                "",
            ).strip()

            licence_class = request.POST.get(
                "license_class",
                "",
            )

            if not all([
                full_name,
                phone_number,
                date_string,
                new_email,
                country,
                city,
                licence_class,
            ]):

                messages.error(
                    request,
                    "Please complete all required fields.",
                )

            elif (
                new_email != request.user.email
                and
                request.session.get(
                    "verified_email"
                ) != new_email
            ):

                messages.error(
                    request,
                    "The new email address must "
                    "be verified first.",
                )

            elif (
                User.objects
                .filter(
                    username=new_email
                )
                .exclude(
                    pk=request.user.pk
                )
                .exists()
            ):

                messages.error(
                    request,
                    "Another account already uses "
                    "that email address.",
                )

            else:

                date_of_birth, date_error = (
                    parse_date_of_birth(
                        date_string
                    )
                )

                if date_error:

                    messages.error(
                        request,
                        date_error,
                    )

                else:

                    new_id_photo = (
                        request.FILES.get(
                            "id_number"
                        )
                    )

                    new_licence_photo = (
                        request.FILES.get(
                            "license_photo"
                        )
                    )

                    # New files are optional while editing.
                    if new_id_photo:

                        error = (
                            validate_uploaded_image(
                                new_id_photo
                            )
                        )

                        if error:
                            messages.error(
                                request,
                                "ID photo: "
                                + error,
                            )

                            return render(
                                request,
                                "onboarding/"
                                "edit_personal_details.html",
                                {
                                    "application":
                                        application
                                },
                            )

                    if new_licence_photo:

                        error = (
                            validate_uploaded_image(
                                new_licence_photo
                            )
                        )

                        if error:
                            messages.error(
                                request,
                                "Licence photo: "
                                + error,
                            )

                            return render(
                                request,
                                "onboarding/"
                                "edit_personal_details.html",
                                {
                                    "application":
                                        application
                                },
                            )

                    with transaction.atomic():

                        request.user.username = (
                            new_email
                        )

                        request.user.email = (
                            new_email
                        )

                        request.user.save(
                            update_fields=[
                                "username",
                                "email",
                            ]
                        )

                        application.full_name = (
                            full_name
                        )

                        application.contact_info = (
                            phone_number
                        )

                        application.date_of_birth = (
                            date_of_birth
                        )

                        application.country_of_origin = (
                            country
                        )

                        application.city = city

                        application.licence_class = (
                            licence_class
                        )

                        if new_id_photo:
                            application.id_photo = (
                                new_id_photo
                            )

                        if new_licence_photo:
                            application.licence_photo = (
                                new_licence_photo
                            )

                        application.save()

                    request.session.pop(
                        "verified_email",
                        None,
                    )

                    messages.success(
                        request,
                        "Personal details updated.",
                    )

                    return redirect(
                        "review_application"
                    )

    return render(
        request,
        "onboarding/edit_personal_details.html",
        {
            "application": application,

            "age": calculate_age(
                application.date_of_birth
            ),

            "otp_seconds_remaining":
                otp_seconds_remaining(
                    request
                ),
        },
    )


# ============================================================
# 12. STEP 3 — VEHICLE DETAILS
# ============================================================

@login_required(
    login_url="sign_in"
)
def vehicle_details(request):

    application = get_object_or_404(
        DriverApplication,
        user=request.user,
    )

    # Submitted applications must not be changed
    if application.status != "Draft":

        return redirect(
            "dashboard"
        )

    if request.method == "POST":

        # These names match your existing HTML inputs.
        registration_plate = request.POST.get(
            "reg_plate",
            "",
        ).strip()

        vehicle_make = request.POST.get(
            "make",
            "",
        ).strip()

        vehicle_model = request.POST.get(
            "model",
            "",
        ).strip()

        vehicle_year = request.POST.get(
            "year",
            "",
        ).strip()

        vehicle_colour = request.POST.get(
            "colour",
            "",
        ).strip()

        country_of_operation = request.POST.get(
            "country",
            "",
        ).strip()

        city_of_work = request.POST.get(
            "city",
            "",
        ).strip()

        if not all([
            registration_plate,
            vehicle_make,
            vehicle_model,
            vehicle_year,
            vehicle_colour,
            country_of_operation,
            city_of_work,
        ]):

            messages.error(
                request,
                "Please complete all vehicle details.",
            )

        else:

            try:
                year_number = int(
                    vehicle_year
                )

            except ValueError:

                messages.error(
                    request,
                    "Please enter a valid vehicle year.",
                )

            else:

                current_year = (
                    timezone.localdate().year
                )

                if (
                    year_number < 1980
                    or
                    year_number > current_year
                ):

                    messages.error(
                        request,
                        (
                            "Vehicle year must be "
                            f"between 1980 and "
                            f"{current_year}."
                        ),
                    )

                else:

                    application.registration_plate = (
                        registration_plate
                    )

                    application.vehicle_make = (
                        vehicle_make
                    )

                    application.vehicle_model = (
                        vehicle_model
                    )

                    application.vehicle_year = (
                        year_number
                    )

                    application.vehicle_colour = (
                        vehicle_colour
                    )

                    application.country_of_operation = (
                        country_of_operation
                    )

                    application.city_of_work = (
                        city_of_work
                    )

                    # Only move the progress forward.
                    if application.current_step < 4:
                        application.current_step = 4

                    application.save()

                    messages.success(
                        request,
                        "Vehicle details saved.",
                    )

                    return redirect(
                        "documents"
                    )

    return render(
        request,
        "onboarding/vehicle_details.html",
        {
            "application": application,
        },
    )


# ============================================================
# 13. STEP 4 — PHOTOS AND DOCUMENTS
# ============================================================

@login_required(
    login_url="sign_in"
)
def documents(request):

    application = get_object_or_404(
        DriverApplication,
        user=request.user,
    )

    if application.status != "Draft":

        return redirect(
            "dashboard"
        )

    if request.method == "POST":

        file_fields = {

            "front_vehicle_photo":
                "Front vehicle photo",

            "rear_vehicle_photo":
                "Rear vehicle photo",

            "cargo_area_photo":
                "Cargo-area photo",

            "vehicle_registration_document":
                "Vehicle registration document",

            "applicant_portrait":
                "Applicant portrait",
        }

        uploaded_files = {}

        # ----------------------------------------------------
        # Validate every newly selected image
        # ----------------------------------------------------

        for field_name, label in file_fields.items():

            uploaded_file = (
                request.FILES.get(
                    field_name
                )
            )

            # If editing, the applicant may leave an existing
            # image unchanged.
            existing_file = getattr(
                application,
                field_name,
            )

            if not uploaded_file and not existing_file:

                messages.error(
                    request,
                    f"{label} is required.",
                )

                return render(
                    request,
                    "onboarding/documents.html",
                    {
                        "application":
                            application
                    },
                )

            if uploaded_file:

                error = validate_uploaded_image(
                    uploaded_file
                )

                if error:

                    messages.error(
                        request,
                        f"{label}: {error}",
                    )

                    return render(
                        request,
                        "onboarding/documents.html",
                        {
                            "application":
                                application
                        },
                    )

                uploaded_files[
                    field_name
                ] = uploaded_file

        # ----------------------------------------------------
        # Save validated files
        # ----------------------------------------------------

        for field_name, uploaded_file in (
            uploaded_files.items()
        ):

            setattr(
                application,
                field_name,
                uploaded_file,
            )

        application.current_step = 5

        application.save()

        messages.success(
            request,
            "Photos and documents saved.",
        )

        return redirect(
            "review_application"
        )

    return render(
        request,
        "onboarding/documents.html",
        {
            "application": application,
        },
    )


# ============================================================
# 14. STEP 5 — REVIEW APPLICATION
# ============================================================

@login_required(
    login_url="sign_in"
)
def review_application(request):

    application = get_object_or_404(
        DriverApplication,
        user=request.user,
    )

    if application.status != "Draft":

        return redirect(
            "dashboard"
        )

    # User should not skip unfinished steps.
    if application.current_step < 5:

        return redirect(
            draft_resume_page(
                application
            )
        )

    missing_fields = (
        find_missing_application_fields(
            application
        )
    )

    return render(
        request,
        "onboarding/review_application.html",
        {
            "application": application,

            "age": calculate_age(
                application.date_of_birth
            ),

            "missing_fields":
                missing_fields,
        },
    )


# ============================================================
# 15. SUBMIT APPLICATION
# ============================================================

@login_required(
    login_url="sign_in"
)
@require_POST
def submit_application(request):

    terms_accepted = (
        request.POST.get(
            "terms_accepted"
        )
        == "on"
    )

    if not terms_accepted:

        messages.error(
            request,
            "You must accept the terms before submitting.",
        )

        return redirect(
            "review_application"
        )

    # transaction.atomic helps make submission one controlled
    # database operation.
    with transaction.atomic():

        application = (
            DriverApplication.objects
            .select_for_update()
            .get(
                user=request.user
            )
        )

        # ----------------------------------------------------
        # Duplicate submission protection
        # ----------------------------------------------------

        if application.status != "Draft":

            return redirect(
                "dashboard"
            )

        missing_fields = (
            find_missing_application_fields(
                application
            )
        )

        if missing_fields:

            messages.error(
                request,
                (
                    "Application cannot be submitted. "
                    "Missing: "
                    + ", ".join(
                        missing_fields
                    )
                ),
            )

            return redirect(
                "review_application"
            )

        application.terms_accepted = True
        application.status = "Submitted"
        application.submitted_at = timezone.now()

        application.save()

    return redirect(
        "submission_success"
    )


# ============================================================
# 16. SUBMISSION SUCCESS PAGE
# ============================================================

@login_required(
    login_url="sign_in"
)
def submission_success(request):

    application = get_object_or_404(
        DriverApplication,
        user=request.user,
    )

    if application.status == "Draft":

        return redirect(
            draft_resume_page(
                application
            )
        )

    return render(
        request,
        "onboarding/submission_success.html",
        {
            "application":
                application
        },
    )


# ============================================================
# 17. DRIVER SIGN-IN
# ============================================================

def sign_in(request):

    if request.user.is_authenticated:

        return redirect(
            "dashboard"
        )

    if request.method == "POST":

        email = (
            request.POST.get(
                "email",
                "",
            )
            .strip()
            .lower()
        )

        password = request.POST.get(
            "password",
            "",
        )

        user = authenticate(
            request,
            username=email,
            password=password,
        )

        if user is None:

            messages.error(
                request,
                "Invalid email or password.",
            )

        else:

            login(
                request,
                user,
            )

            if user.is_staff:
                return redirect("admin:index")

            application = DriverApplication.objects.filter(user=user).first()
            if application is None:
                return redirect("choose_transport")

            # Draft applicants resume where they stopped.
            if application.status == "Draft":

                return redirect(
                    draft_resume_page(
                        application
                    )
                )

            return redirect(
                "dashboard"
            )

    return render(
        request,
        "onboarding/sign_in.html",
    )


# ============================================================
# 18. DRIVER DASHBOARD
# ============================================================
@login_required(login_url="sign_in")
def dashboard(request):

    # Staff/admin accounts are management accounts,
    # not driver accounts.
    if request.user.is_staff:
        return redirect("admin:index")

    try:
        application = DriverApplication.objects.get(
            user=request.user
        )
    except DriverApplication.DoesNotExist:
        return redirect("choose_transport")

    # Database stores "Submitted".
    # Driver sees "Under review".
    if application.status == "Submitted":
        display_status = "Under review"
    else:
        display_status = application.status

    return render(
        request,
        "onboarding/dashboard.html",
        {
            "application": application,
            "display_status": display_status,
            "age": calculate_age(
                application.date_of_birth
            ),
        },
    )

# ============================================================
# 19. SIGN OUT
# ============================================================

@login_required(
    login_url="sign_in"
)
def sign_out(request):

    logout(request)

    return redirect(
        "home"
    )