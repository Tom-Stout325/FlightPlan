# operations/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from . import views

app_name = "operations"

urlpatterns = [
    path("ops-plans/", views.OpsPlanIndexView.as_view(), name="ops_plan_index"),
    path(
        "events/<int:event_id>/ops-plans/",
        views.OpsPlanListView.as_view(),
        name="ops_plan_list",
    ),
    path(
        "events/<int:event_id>/ops-plans/new/",
        views.OpsPlanCreateView.as_view(),
        name="ops_plan_create",
    ),
    path(
        "ops-plans/<int:pk>/",
        views.OpsPlanDetailView.as_view(),
        name="ops_plan_detail",
    ),
    path(
        "ops-plans/<int:pk>/edit/",
        views.OpsPlanUpdateView.as_view(),
        name="ops_plan_update",
    ),
    path("ops-plans/<int:pk>/pdf/", views.ops_plan_pdf_view, name="ops_plan_pdf"),
    path(
        "ops-plans/<int:pk>/delete/",
        views.OpsPlanDeleteView.as_view(),
        name="ops_plan_delete",
    ),
    path(
        "ops-plans/<int:pk>/submit/",
        views.ops_plan_submit_view,
        name="ops_plan_submit",
    ),
    path(
        "ops-plans/<int:pk>/approve/",
        views.ops_plan_approve_view,
        name="ops_plan_approve",
    ),
    path(
        "ops-plans/<int:pk>/archive/",
        views.ops_plan_archive_view,
        name="ops_plan_archive",
    ),

    # Token-based client approval page (distinct name!)
    path(
        "ops/<int:pk>/approve/<str:token>/",
        views.OpsPlanApprovalView.as_view(),
        name="ops_plan_approve_token",
    ),

    # Misc ops actions
    # path("ops/<int:pk>/send-approval/", views.send_approval_request, name="ops_plan_send_approval"),
    path(
        "ops/<int:pk>/status/<str:new_status>/",
        views.change_ops_plan_status,
        name="ops_plan_change_status",
    ),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
