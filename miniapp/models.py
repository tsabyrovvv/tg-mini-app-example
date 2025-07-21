from django.db import models
from django.utils import timezone

class TelegramUser(models.Model):
    telegram_id = models.BigIntegerField(unique=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    username = models.CharField(max_length=100, blank=True)
    language_code = models.CharField(max_length=10, blank=True)
    is_premium = models.BooleanField(default=False)
    is_bot = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.first_name} {self.last_name} (@{self.username})"
    
    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()
    
    @property
    def days_since_join(self):
        return (timezone.now() - self.created_at).days

class UserSession(models.Model):
    user = models.ForeignKey(TelegramUser, on_delete=models.CASCADE)
    session_start = models.DateTimeField(auto_now_add=True)
    session_end = models.DateTimeField(null=True, blank=True)
    platform = models.CharField(max_length=50, blank=True)
    version = models.CharField(max_length=20, blank=True)
    
    def __str__(self):
        return f"Сессия {self.user.first_name} - {self.session_start}"

class UserStats(models.Model):
    user = models.OneToOneField(TelegramUser, on_delete=models.CASCADE)
    total_visits = models.IntegerField(default=0)
    total_time_spent = models.DurationField(default=timezone.timedelta)
    last_visit = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"Статистика {self.user.first_name}"
    