from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.index, name='index'),
    path('health/', views.health, name='health'),
    path('api/auth/register/', views.register_user, name='register_user'),
    path('api/auth/login/', views.login_user, name='login_user'),
    path('api/auth/logout/', views.logout_user, name='logout_user'),
    path('api/auth/profile/', views.user_profile, name='user_profile'),
    path('api/cards/', views.cards_catalog, name='cards_catalog'),
    path('api/decks/', views.decks_list_create, name='decks_list_create'),
    path('api/decks/<int:deck_id>/', views.deck_detail, name='deck_detail'),
    path('api/match/create/', views.create_match, name='create_match'),
    path('api/match/<str:room_code>/', views.get_match, name='get_match'),
    path('api/match/<str:room_code>/join/', views.join_match, name='join_match'),
    path('api/match/<str:room_code>/action/', views.match_action, name='match_action'),
    path('api/match/<str:room_code>/draw/', views.draw_card, name='draw_card'),
    path('api/match/<str:room_code>/summon/', views.summon_unit, name='summon_unit'),
    path('api/match/<str:room_code>/move/', views.move_unit, name='move_unit'),
    path('api/match/<str:room_code>/attack/', views.attack_unit, name='attack_unit'),
    path('api/match/<str:room_code>/end-turn/', views.end_turn, name='end_turn'),
]
