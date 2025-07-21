import hashlib
import hmac
import json
from urllib.parse import parse_qsl
from django.conf import settings

def validate_telegram_data(init_data):
    try:
        parsed_data = dict(parse_qsl(init_data))
        hash_value = parsed_data.pop('hash', '')
        
        data_check_string = '\n'.join([f'{k}={v}' for k, v in sorted(parsed_data.items())])
        
        secret_key = hmac.new(
            settings.TELEGRAM_BOT_TOKEN.encode(), 
            b"WebAppData",
            hashlib.sha256
        ).digest()
        
        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return calculated_hash == hash_value, parsed_data
    except Exception:
        return False, {}

def parse_user_data(telegram_data):
    """Парсинг данных пользователя из Telegram"""
    try:
        user_json = telegram_data.get('user', '{}')
        user_data = json.loads(user_json) if isinstance(user_json, str) else user_json
        return user_data
    except (json.JSONDecodeError, KeyError):
        return {}
    