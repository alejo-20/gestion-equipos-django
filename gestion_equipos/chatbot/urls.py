from django.urls import path

from . import views

app_name = "chatbot"

urlpatterns = [
    path("", views.chat, name="chat"),
    path("api/mensaje/", views.api_mensaje, name="api_mensaje"),
]
