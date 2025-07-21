import json
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from .models import TelegramUser, UserSession, UserStats
from .utils import validate_telegram_data, parse_user_data

class IndexView(View):
    def get(self, request):
        return render(request, 'miniapp/index.html')

@csrf_exempt
@require_http_methods(["POST"])
def auth_user(request):
    """Аутентификация пользователя через Telegram WebApp"""
    try:
        data = json.loads(request.body)
        init_data = data.get('initData', '')
        
        # В продакшене обязательно валидировать данные
        # is_valid, telegram_data = validate_telegram_data(init_data)
        # if not is_valid:
        #     return JsonResponse({'error': 'Invalid data'}, status=400)
        
        # Для демо парсим данные напрямую
        user_data = data.get('user', {})
        platform_data = data.get('platform', {})
        
        if not user_data.get('id'):
            return JsonResponse({'error': 'User data missing'}, status=400)
        
        # Создаем или обновляем пользователя
        user, created = TelegramUser.objects.get_or_create(
            telegram_id=user_data['id'],
            defaults={
                'first_name': user_data.get('first_name', ''),
                'last_name': user_data.get('last_name', ''),
                'username': user_data.get('username', ''),
                'language_code': user_data.get('language_code', ''),
                'is_premium': user_data.get('is_premium', False),
                'is_bot': user_data.get('is_bot', False),
            }
        )
        
        # Обновляем данные если пользователь уже существует
        if not created:
            user.first_name = user_data.get('first_name', user.first_name)
            user.last_name = user_data.get('last_name', user.last_name)
            user.username = user_data.get('username', user.username)
            user.language_code = user_data.get('language_code', user.language_code)
            user.is_premium = user_data.get('is_premium', user.is_premium)
            user.save()
        
        # Создаем сессию
        session = UserSession.objects.create(
            user=user,
            platform=platform_data.get('platform', ''),
            version=platform_data.get('version', '')
        )
        
        # Обновляем статистику
        stats, stats_created = UserStats.objects.get_or_create(
            user=user,
            defaults={'total_visits': 1}
        )
        if not stats_created:
            stats.total_visits += 1
            stats.save()
        
        return JsonResponse({
            'success': True,
            'user_id': user.telegram_id,
            'session_id': session.id,
            'created': created
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_user_data(request, user_id):
    """Получение данных пользователя"""
    try:
        user = get_object_or_404(TelegramUser, telegram_id=user_id)
        stats = UserStats.objects.get_or_create(user=user)[0]
        
        return JsonResponse({
            'user': {
                'id': user.telegram_id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'language_code': user.language_code,
                'is_premium': user.is_premium,
                'full_name': user.full_name,
                'days_since_join': user.days_since_join,
            },
            'stats': {
                'total_visits': stats.total_visits,
                'last_visit': stats.last_visit.isoformat(),
                'member_since': user.created_at.isoformat(),
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def update_session(request, user_id):
    """Обновление данных сессии"""
    try:
        data = json.loads(request.body)
        user = get_object_or_404(TelegramUser, telegram_id=user_id)
        
        # Находим последнюю активную сессию
        session = UserSession.objects.filter(
            user=user, 
            session_end__isnull=True
        ).first()
        
        if session and data.get('action') == 'end':
            session.session_end = timezone.now()
            session.save()
            
            # Обновляем общее время
            session_duration = session.session_end - session.session_start
            stats = UserStats.objects.get_or_create(user=user)[0]
            stats.total_time_spent += session_duration
            stats.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_user_avatar(request, user_id):
    """Получение аватара пользователя (заглушка)"""
    # В реальном приложении здесь был бы запрос к Telegram Bot API
    # для получения фото профиля пользователя
    avatar_url = f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}"
    return JsonResponse({'avatar_url': avatar_url})
