import json
import logging
import requests
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from django.views import View
from django.utils import timezone
from django.conf import settings
from django.core.cache import cache
from .models import TelegramUser, UserSession, UserStats
from .utils import validate_telegram_data, parse_user_data

logger = logging.getLogger(__name__)

class IndexView(View):
    """Главная страница приложения"""
    def get(self, request):
        return render(request, 'miniapp/index.html')

@csrf_exempt
@require_http_methods(["POST"])
def auth_user(request):
    """Аутентификация пользователя через Telegram WebApp"""
    try:
        # Логируем входящие данные для отладки
        logger.info(f"Request body: {request.body}")
        
        data = json.loads(request.body)
        init_data = data.get('initData', '')
        
        # В продакшене обязательно валидировать данные
        # is_valid, telegram_data = validate_telegram_data(init_data)
        # if not is_valid:
        #     return JsonResponse({'error': 'Invalid data'}, status=400)
        
        # Получаем данные пользователя
        user_data = data.get('user', {})
        platform_data = data.get('platform', {})
        
        # Проверяем наличие обязательных данных
        if not user_data or not user_data.get('id'):
            logger.error(f"Missing user data: {user_data}")
            return JsonResponse({'error': 'User data missing', 'details': 'No user ID provided'}, status=400)
        
        # Создаем или обновляем пользователя
        try:
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
                
            logger.info(f"User {'created' if created else 'updated'}: {user.telegram_id}")
            
        except Exception as e:
            logger.error(f"Error creating/updating user: {e}")
            return JsonResponse({'error': 'Database error', 'details': str(e)}, status=500)
        
        # Создаем сессию
        try:
            session = UserSession.objects.create(
                user=user,
                platform=platform_data.get('platform', ''),
                version=platform_data.get('version', '')
            )
            logger.info(f"Session created: {session.id}")
        except Exception as e:
            logger.error(f"Error creating session: {e}")
            return JsonResponse({'error': 'Session creation failed', 'details': str(e)}, status=500)
        
        # Обновляем статистику
        try:
            stats, stats_created = UserStats.objects.get_or_create(
                user=user,
                defaults={'total_visits': 1}
            )
            if not stats_created:
                stats.total_visits += 1
                stats.save()
                
            logger.info(f"Stats updated: visits = {stats.total_visits}")
        except Exception as e:
            logger.error(f"Error updating stats: {e}")
            # Не критично, продолжаем
        
        return JsonResponse({
            'success': True,
            'user_id': user.telegram_id,
            'session_id': session.id,
            'created': created
        })
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse({'error': 'Invalid JSON', 'details': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Unexpected error in auth_user: {e}")
        return JsonResponse({'error': 'Internal server error', 'details': str(e)}, status=500)

@require_http_methods(["GET"])
def get_user_data(request, user_id):
    """Получение данных пользователя"""
    try:
        user = get_object_or_404(TelegramUser, telegram_id=user_id)
        stats, _ = UserStats.objects.get_or_create(
            user=user,
            defaults={'total_visits': 1}
        )
        
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
        logger.error(f"Error getting user data: {e}")
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
            stats, _ = UserStats.objects.get_or_create(user=user)
            stats.total_time_spent += session_duration
            stats.save()
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error updating session: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@require_http_methods(["GET"])
def get_user_avatar(request, user_id):
    """Получение аватара пользователя через Telegram Bot API"""
    try:
        # Проверяем наличие токена бота
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured")
            return _get_fallback_avatar(user_id)
        
        # Проверяем существование пользователя в нашей БД
        user = get_object_or_404(TelegramUser, telegram_id=user_id)
        
        # Проверяем кэш (кэшируем на 1 час)
        cache_key = f"user_avatar_{user_id}"
        cached_avatar = cache.get(cache_key)
        if cached_avatar:
            logger.info(f"Avatar served from cache for user {user_id}")
            return JsonResponse({'avatar_url': cached_avatar, 'cached': True})
        
        # Получаем фото профиля через Telegram Bot API
        avatar_url = _fetch_telegram_avatar(bot_token, user_id)
        
        if avatar_url:
            # Кэшируем результат на 1 час
            cache.set(cache_key, avatar_url, 3600)
            logger.info(f"Avatar fetched and cached for user {user_id}")
            return JsonResponse({
                'avatar_url': avatar_url,
                'cached': False,
                'source': 'telegram'
            })
        else:
            # Если не удалось получить аватар из Telegram, используем fallback
            fallback_url = _get_fallback_avatar(user_id)
            return JsonResponse({
                'avatar_url': fallback_url,
                'cached': False,
                'source': 'fallback'
            })
            
    except Exception as e:
        logger.error(f"Error getting avatar for user {user_id}: {e}")
        # В случае ошибки возвращаем fallback аватар
        fallback_url = _get_fallback_avatar(user_id)
        return JsonResponse({
            'avatar_url': fallback_url,
            'error': str(e),
            'source': 'fallback'
        })

def _fetch_telegram_avatar(bot_token: str, user_id: int) -> str:
    """Получение аватара пользователя через Telegram Bot API"""
    try:
        # Шаг 1: Получаем фотографии профиля пользователя
        get_photos_url = f"https://api.telegram.org/bot{bot_token}/getUserProfilePhotos"
        photos_params = {
            'user_id': user_id,
            'limit': 1  # Получаем только последнее фото
        }
        
        logger.info(f"Requesting profile photos for user {user_id}")
        photos_response = requests.get(get_photos_url, params=photos_params, timeout=10)
        photos_response.raise_for_status()
        photos_data = photos_response.json()
        
        if not photos_data.get('ok'):
            logger.warning(f"Telegram API error: {photos_data.get('description', 'Unknown error')}")
            return None
        
        photos = photos_data.get('result', {}).get('photos', [])
        if not photos or not photos[0]:
            logger.info(f"No profile photos found for user {user_id}")
            return None
        
        # Берем фото наибольшего размера
        photo_sizes = photos[0]  # Первое (последнее загруженное) фото
        largest_photo = max(photo_sizes, key=lambda x: x.get('file_size', 0))
        file_id = largest_photo['file_id']
        
        logger.info(f"Found photo with file_id: {file_id}")
        
        # Шаг 2: Получаем путь к файлу
        get_file_url = f"https://api.telegram.org/bot{bot_token}/getFile"
        file_params = {'file_id': file_id}
        
        file_response = requests.get(get_file_url, params=file_params, timeout=10)
        file_response.raise_for_status()
        file_data = file_response.json()
        
        if not file_data.get('ok'):
            logger.warning(f"Failed to get file info: {file_data.get('description', 'Unknown error')}")
            return None
        
        file_path = file_data.get('result', {}).get('file_path')
        if not file_path:
            logger.warning(f"No file path in response for user {user_id}")
            return None
        
        # Шаг 3: Формируем URL для скачивания
        download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
        
        # Проверяем доступность файла
        head_response = requests.head(download_url, timeout=5)
        if head_response.status_code == 200:
            logger.info(f"Avatar URL generated successfully for user {user_id}")
            return download_url
        else:
            logger.warning(f"Avatar file not accessible for user {user_id}")
            return None
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout when fetching avatar for user {user_id}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error when fetching avatar for user {user_id}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error when fetching avatar for user {user_id}: {e}")
        return None

def _get_fallback_avatar(user_id: int) -> str:
    """Генерирует fallback аватар"""
    # Варианты fallback аватаров
    fallback_services = [
        f"https://api.dicebear.com/7.x/avataaars/svg?seed={user_id}",
        f"https://api.dicebear.com/7.x/initials/svg?seed={user_id}",
        f"https://robohash.org/{user_id}?set=set4&size=200x200",
        f"https://ui-avatars.com/api/?name=User+{user_id}&background=random&size=200"
    ]
    
    # Выбираем fallback на основе user_id для консистентности
    selected_service = fallback_services[user_id % len(fallback_services)]
    logger.info(f"Using fallback avatar service for user {user_id}: {selected_service}")
    
    return selected_service

# Дополнительные функции для управления кэшем
@csrf_exempt
@require_http_methods(["POST"])
def refresh_user_avatar(request, user_id):
    """Принудительное обновление аватара пользователя"""
    try:
        # Очищаем кэш
        cache_key = f"user_avatar_{user_id}"
        cache.delete(cache_key)
        
        # Получаем новый аватар
        return get_user_avatar(request, user_id)
        
    except Exception as e:
        logger.error(f"Error refreshing avatar for user {user_id}: {e}")
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def clear_all_avatars_cache(request):
    """Очистка всего кэша аватаров (только для админов)"""
    try:
        # В простой реализации - здесь можно добавить проверку прав
        # Для production лучше использовать tagged cache или отдельное хранилище
        
        # Очищаем весь кэш (осторожно в продакшене!)
        cache.clear()
        
        logger.info("All avatars cache cleared")
        return JsonResponse({'success': True, 'message': 'All avatars cache cleared'})
        
    except Exception as e:
        logger.error(f"Error clearing avatars cache: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    