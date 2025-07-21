from django.contrib import admin
from .models import TelegramUser, UserSession, UserStats

@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ('telegram_id', 'first_name', 'last_name', 'username', 'is_premium', 'created_at', 'last_seen')
    list_filter = ('is_premium', 'is_bot', 'language_code', 'created_at')
    search_fields = ('first_name', 'last_name', 'username', 'telegram_id')
    readonly_fields = ('created_at', 'last_seen')

@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'session_start', 'session_end', 'platform', 'version')
    list_filter = ('platform', 'session_start')
    search_fields = ('user__first_name', 'user__last_name', 'user__username')

@admin.register(UserStats)
class UserStatsAdmin(admin.ModelAdmin):
    list_display = ('user', 'total_visits', 'last_visit', 'total_time_spent')
    search_fields = ('user__first_name', 'user__last_name', 'user__username')
    readonly_fields = ('last_visit',)
    