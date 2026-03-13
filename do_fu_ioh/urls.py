from django.contrib import admin
from django.urls import path

from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('health/', views.health, name='health'),
    path('api/cards/', views.cards_catalog, name='cards_catalog'),
    path('api/match/active/', views.get_active_match, name='get_active_match'),
    path('api/match/create-vs-ai/', views.create_match_vs_ai, name='create_match_vs_ai'),
    path('api/match/<str:room_code>/', views.get_match, name='get_match'),
    path('api/match/<str:room_code>/action/', views.match_action, name='match_action'),
]
