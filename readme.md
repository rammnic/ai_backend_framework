# AI Backend Framework

**Headless AI-оркестратор для создания пайплайнов искусственного интеллекта**

## Описание

AI Backend Framework — это Python-библиотека и микросервис для создания и выполнения AI-пайплайнов. Фреймворк предоставляет готовые "атомы" (nodes) для типовых операций с AI и позволяет собирать из них сложные цепочки обработки данных.

### Ключевые возможности

- 🧩 **Модульная архитектура** — собирай пайплайны из готовых блоков
- 🔄 **Оркестрация** — условное ветвление (if/else) и маршрутизация данных
- 📡 **Стриминг** — потоковая передача ответов от LLM
- 🌐 **REST API** — готовый микросервис на FastAPI
- 🐛 **Отладка** — встроенный Debugger для каждого шага
- ⚙️ **Конфигурация** — JSON/YAML или Python DSL

## Установка

```bash
# Клонировать репозиторий
git clone https://github.com/rammnic/ai_backend_framework.git
cd ai-backend-framework

# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или
venv\Scripts\activate  # Windows

# Установить зависимости
pip install -r requirements.txt

# Скопировать и настроить .env
cp .env.example .env
# Отредактировать .env, добавив OPENROUTER_API_KEY
```

## Быстрый старт

### Python DSL

```python
import asyncio
from ai_flow_engine import Context, PipelineRunner
from ai_flow_engine.nodes import LLMNode, PromptNode

async def main():
    # Создаём пайплайн
    pipeline = [
        PromptNode(
            template="Объясни простыми словами: {{ user_input }}",
            output_key="prompt"
        ),
        LLMNode(
            model="openai/gpt-4o-mini",
            input_key="prompt",
            output_key="response"
        )
    ]
    
    # Запускаем
    runner = PipelineRunner()
    context = Context(data={"user_input": "квантовые вычисления"})
    result = await runner.execute(pipeline, context)
    
    print(result.get("response"))

asyncio.run(main())
```

### JSON конфигурация

```json
{
  "name": "chat",
  "nodes": [
    {
      "type": "LLMNode",
      "name": "chat",
      "config": {
        "model": "openai/gpt-4o-mini",
        "include_history": true
      }
    }
  ]
}
```

```python
from ai_flow_engine.config import load_pipeline_from_file

pipeline = load_pipeline_from_file("pipelines/chat.json")
result = await runner.execute(pipeline, context)
```

### REST API

```bash
# Запустить сервер
uvicorn api.main:app --reload

# Открыть документацию
# http://localhost:8000/docs
```

## Архитектура

```
ai-backend-framework/
├── ai_flow_engine/
│   ├── core/           # Ядро
│   │   ├── context.py  # Контекст — шина данных
│   │   ├── base_node.py # Базовый класс ноды
│   │   ├── engine.py   # PipelineRunner
│   │   └── debugger.py # Отладка
│   ├── nodes/          # Готовые ноды
│   │   ├── llm_node.py
│   │   ├── prompt_node.py
│   │   ├── condition_node.py
│   │   ├── web_search_node.py
│   │   └── image_analysis_node.py
│   └── config/         # Загрузка конфигурации
├── api/                # FastAPI REST API
└── examples/           # Примеры
```

## Встроенные ноды

| Нода | Описание |
|------|----------|
| `LLMNode` | Запросы к LLM через OpenRouter |
| `PromptNode` | Шаблоны промптов (Jinja2) |
| `ConditionNode` | Условное ветвление |
| `SwitchNode` | Множественный выбор |
| `WebSearchNode` | Веб-поиск (DuckDuckGo/SerpAPI) |
| `WebFetchNode` | Загрузка веб-страниц |
| `ImageAnalysisNode` | Анализ изображений (Vision) |
| `ImageGenerationNode` | Генерация изображений |

## API Endpoints

| Метод | Путь | Описание |
|-------|------|----------|
| `GET` | `/health` | Проверка здоровья |
| `GET` | `/pipelines` | Список пайплайнов |
| `POST` | `/execute` | Выполнить пайплайн |
| `POST` | `/execute/stream` | Выполнить со стримингом |
| `POST` | `/chat` | Простой чат с LLM |
| `POST` | `/chat/stream` | Чат со стримингом |
| `POST` | `/search` | Веб-поиск |
| `POST` | `/analyze-image` | Анализ изображения |

## Создание собственной ноды

```python
from ai_flow_engine import BaseNode, Context

class MyCustomNode(BaseNode):
    """Моя кастомная нода"""
    
    async def run(self, context: Context) -> Context:
        # Читаем данные из контекста
        input_data = context.get("user_input")
        
        # Обрабатываем
        result = self._process(input_data)
        
        # Записываем в контекст
        context.set("my_output", result)
        
        return context
    
    def _process(self, data):
        return data.upper()
```

## Переменные окружения

| Переменная | Описание |
|------------|----------|
| `OPENROUTER_API_KEY` | API ключ OpenRouter (обязательно) |
| `OPENROUTER_API_URL` | URL API OpenRouter |
| `SERPAPI_KEY` | API ключ SerpAPI (опционально) |

## Лицензия

MIT License

## Автор

Николай (rammnic)