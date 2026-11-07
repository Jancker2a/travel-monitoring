# 🎯 Travel Price Monitor

Автоматический мониторинг цен на путешествия с сайта fly.pl для поиска выгодных предложений.

## 🚀 Возможности

- **Автоматический парсинг** предложений с fly.pl
- **Накопительное хранение** данных (каждый запуск добавляет новые данные)
- **Визуализация** изменений цен с помощью графиков
- **Автоматические отчеты** с анализом трендов
- **Планировщик** для регулярного мониторинга
- **Уведомления** о значительных изменениях цен
- **🛫 Сравнение аэропортов** - поиск выгодных предложений из разных городов
- **📊 Расширенные дашборды** с поддержкой сравнения аэропортов

## 📋 Требования

- Python 3.8+
- Playwright
- pandas
- matplotlib

## 🛠 Быстрая установка

```bash
# Клонируйте репозиторий
git clone <repository-url>
cd travel-price-monitor

# Установите зависимости
pip install -r requirements.txt

# Установите браузеры
playwright install chromium

# Запустите мониторинг
python travel_monitor.py
```

## 🎯 Использование

### Основной скрипт

```bash
python travel_monitor.py
```

### Анализ данных

```bash
python analyze_data.py --charts
```

### Автоматический мониторинг

```bash
python scheduler.py
```

### Параллельный мониторинг всех фильтров

```bash
python scripts/run_monitors_parallel.py -j 3
```

### Генерация интерактивных дашбордов и каталога

```bash
# Все дашборды, лэндинг и каталог отелей:
python scripts/run_dashboards_parallel.py -j 3

# Или генерация одного конкретного фильтра:
python generate_inline_charts_dashboard.py --data-file data/filters/filter_turkey_7_10_days/travel_prices.csv --output index_filter_turkey_7_10_days.html
```

## 📊 Результаты

- `data/travel_prices.csv` - собранные данные
- `data/charts/` - графики цен
- `data/price_report.txt` - текстовый отчет
- `data/*_airport_comparison.json` - результаты сравнения аэропортов
- `data/*_airport_comparison_report.txt` - отчеты о сравнении аэропортов
- `index_airports.html` - главная страница с дашбордами сравнения аэропортов

## ⚙️ Настройка

Отредактируйте `config.json` для изменения параметров поиска и мониторинга.

## 📈 Автоматизация

Настройте cron или Task Scheduler для регулярного запуска:

```bash
# Ежедневно в 9:00
0 9 * * * cd /path/to/travel-price-monitor && python travel_monitor.py
```

---

**Удачного мониторинга цен! 🎯✈️**

