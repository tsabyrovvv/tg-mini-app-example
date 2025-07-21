from django.urls import path
from . import views

app_name = 'miniapp'

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('api/auth/', views.auth_user, name='auth_user'),
    path('api/user/<int:user_id>/', views.get_user_data, name='get_user_data'),
    path('api/user/<int:user_id>/session/', views.update_session, name='update_session'),
    path('api/user/<int:user_id>/avatar/', views.get_user_avatar, name='get_user_avatar'),
    
    # Дополнительные эндпоинты для управления кэшем аватаров
    path('api/user/<int:user_id>/avatar/refresh/', views.refresh_user_avatar, name='refresh_user_avatar'),
    path('api/admin/avatars/clear/', views.clear_all_avatars_cache, name='clear_avatars_cache'),
]
