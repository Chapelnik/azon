# Карта концертов группы АЗОН

Веб-приложение для парсинга и отображения концертов на карте.

## 🚀 Быстрый старт

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск приложения
python app.py
```

Откройте http://localhost:5000 в браузере.

## 📁 Структура проекта

```
/workspace/
├── app.py                 # Основное приложение (оригинальная версия)
├── app_refactored.py      # Рефакторированная версия с модульной архитектурой
├── config.json            # Конфигурация приложения
├── scraper/
│   └── __init__.py        # Модуль парсинга с retry-логикой и валидацией
├── cache/
│   └── __init__.py        # Модуль кэширования (FileCache, RedisCache)
├── geocoder.py            # Геокодер с rate limiting и fallback
├── logging_config.py      # Настройка логирования и health checks
├── templates/
│   └── index.html         # HTML шаблон с улучшенным UI
├── tests/
│   └── test_app.py        # Тесты pytest
└── requirements.txt       # Зависимости
```

## 🔧 Реализованные улучшения

### 2. Устойчивость (Retry Logic)
- Автоматические повторные запросы при ошибках сети
- Экспоненциальная задержка между попытками
- Обработка статусов 429, 500, 502, 503, 504

### 3. Производительность (Rate Limiting)
- Rate limiter для API запросов (1 запрос/сек)
- Кэш известных городов для мгновенного доступа
- Пакетная обработка геокодирования

### 4. Архитектура (Modular Design)
Разделение кода на независимые модули:
- `scraper/` - Парсинг данных
- `cache/` - Кэширование (File/Redis)
- `geocoder.py` - Геокодирование
- `logging_config.py` - Логирование

### 5. Валидация (Data Validation)
- Проверка формата дат
- Фильтрация прошедших событий (с буфером 7 дней)
- Валидация названий городов (~60 городов России)

### 7. Логирование (Structured Logging + Health Check)
- JSON формат логов для production
- Health check endpoint `/api/health`
- Мониторинг компонентов (scraper, cache, geocoder)

### 8. Тестирование (Pytest Tests)
Покрытие тестами ключевых компонентов:
- ConcertScraper (валидация, парсинг)
- FileCache (сохранение, загрузка, TTL)
- GeocodeCache (кэширование координат)
- RateLimiter (ограничение частоты)
- GeocoderService (известные города)

### 9. Frontend (UX Improvements)
- Индикатор загрузки с анимацией
- Обработка ошибок с понятными сообщениями
- Кнопка обновления данных
- Индикатор состояния системы
- Адаптивный дизайн для мобильных

### 11. Документация (Documentation)
- Расширенный README с примерами
- Type hints во всех модулях
- Docstrings для классов и методов

### 12. Code Quality
- Исправлены bare except блоки
- Добавлены type hints
- Следование PEP 8
- Модульная структура

## 🔐 Безопасность

Используйте переменные окружения для чувствительных данных:

```bash
# .env файл
CARTO_API_KEY=your_key_here
CARTO_USERNAME=your_username
REDIS_HOST=localhost
SECRET_KEY=your_secret_key
ADMIN_API_KEY=your_admin_key
```

## 📊 API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/` | GET | Главная страница с картой |
| `/api/concerts` | GET | Список концертов с координатами |
| `/api/stats` | GET | Статистика приложения |
| `/api/health` | GET | Health check |
| `/api/refresh` | POST | Принудительное обновление кэша |

## 🧪 Тестирование

```bash
# Запустить все тесты
pytest tests/ -v

# Запустить с покрытием
pytest tests/ --cov=. --cov-report=html

# Запустить конкретный тест
pytest tests/test_app.py::TestConcertScraper::test_date_validation_valid -v
```

## ⚙️ Конфигурация

`config.json`:

```json
{
  "carto": {
    "api_key": "YOUR_CARTO_API_KEY",
    "username": "YOUR_USERNAME"
  },
  "cache": {
    "enabled": true,
    "file_path": ".cache/concerts_cache.json",
    "ttl_hours": 24
  },
  "redis": {
    "enabled": false,
    "host": "localhost",
    "port": 6379
  },
  "scraper": {
    "timeout": 10,
    "max_retries": 3
  },
  "geocoder": {
    "timeout": 5,
    "rate_limit": 1.0,
    "max_retries": 2
  },
  "logging": {
    "level": "INFO",
    "file": "logs/app.log",
    "structured": false
  },
  "app": {
    "host": "0.0.0.0",
    "port": 5000,
    "debug": false
  }
}
```

## 📝 Лицензия

MIT
