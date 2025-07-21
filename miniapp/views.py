import requests
import logging
from django.conf import settings
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.shortcuts import get_object_or_404
from .models import TelegramUser

logger = logging.getLogger(__name__)

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

# Дополнительная функция для предзагрузки аватаров (можно вызывать из celery task)
def preload_user_avatar(user_id: int) -> bool:
    """Предзагрузка аватара пользователя в кэш"""
    try:
        bot_token = settings.TELEGRAM_BOT_TOKEN
        if not bot_token:
            return False
        
        cache_key = f"user_avatar_{user_id}"
        if cache.get(cache_key):
            return True  # Уже в кэше
        
        avatar_url = _fetch_telegram_avatar(bot_token, user_id)
        if avatar_url:
            cache.set(cache_key, avatar_url, 3600)
            logger.info(f"Avatar preloaded for user {user_id}")
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error preloading avatar for user {user_id}: {e}")
        return False

# Функция для очистки кэша аватаров
def clear_avatar_cache(user_id: int = None) -> bool:
    """Очистка кэша аватаров"""
    try:
        if user_id:
            cache_key = f"user_avatar_{user_id}"
            cache.delete(cache_key)
            logger.info(f"Avatar cache cleared for user {user_id}")
        else:
            # Очистка всех аватаров (требует специальной настройки кэша)
            # Это упрощенная версия - в продакшене лучше использовать tagged cache
            logger.warning("Clearing all avatar cache not implemented in this version")
        
        return True
    except Exception as e:
        logger.error(f"Error clearing avatar cache: {e}")
        return False
    