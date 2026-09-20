from django.urls import path

from . import views


urlpatterns = [

    # 1. Entry page
    path(
        "",
        views.home,
        name="home",
    ),

    # 2. Step 1
    path(
        "transport/",
        views.choose_transport,
        name="choose_transport",
    ),

    # 3. Step 2
    path(
        "personal-details/",
        views.personal_details,
        name="personal_details",
    ),

    # 4. Editing Step 2 after account creation
    path(
        "edit-personal-details/",
        views.edit_personal_details,
        name="edit_personal_details",
    ),

    # 5. Step 3
    path(
        "vehicle-details/",
        views.vehicle_details,
        name="vehicle_details",
    ),

    # 6. Step 4
    path(
        "documents/",
        views.documents,
        name="documents",
    ),

    # 7. Step 5
    path(
        "review/",
        views.review_application,
        name="review_application",
    ),

    # 8. Submit application
    path(
        "submit/",
        views.submit_application,
        name="submit_application",
    ),

    # 9. Success page
    path(
        "submitted/",
        views.submission_success,
        name="submission_success",
    ),

    # 10. Authentication
    path(
        "sign-in/",
        views.sign_in,
        name="sign_in",
    ),

    path(
        "sign-out/",
        views.sign_out,
        name="sign_out",
    ),

    # 11. Driver dashboard
    path(
        "dashboard/",
        views.dashboard,
        name="dashboard",
    ),
]