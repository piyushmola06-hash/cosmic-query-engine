from django.urls import path
from api.views import (
    CollectView,
    QueryView,
    SessionEndView,
    SessionStartView,
    TrailView,
)

urlpatterns = [
    path("session/start/", SessionStartView.as_view(), name="session-start"),
    path("session/<uuid:session_id>/collect/", CollectView.as_view(), name="session-collect"),
    path("session/<uuid:session_id>/query/", QueryView.as_view(), name="session-query"),
    path("session/<uuid:session_id>/trail/", TrailView.as_view(), name="session-trail"),
    path("session/<uuid:session_id>/end/", SessionEndView.as_view(), name="session-end"),
]
