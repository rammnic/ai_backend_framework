# Руководство пользователя AI Backend Framework

## Содержание

1. [Основные концепции](#основные-концепции)
2. [Context — шина данных](#context--шина-данных)
3. [Nodes — атомарные операции](#nodes--атомарные-операции)
4. [Pipeline — пайплайн](#pipeline--пайплайн)
5. [Конфигурация пайплайнов](#конфигурация-пайплайнов)
6. [API Reference](#api-reference)
7. [Примеры использования](#примеры-использования)
8. [Отладка](#отладка)

---

## Основные концепции

### Архитектура

AI Backend Framework построен на трёх ключевых концепциях:

1. **Context (Контекст)** — "шина данных", которая передаётся между всеми нодами
2. **Node (Атом)** — атомарная операция: читает из Context, обрабатывает, пишет в Context
3. **Pipeline (Пайплайн)** — последовательность нод, выполняемая движком

### Поток данных

```
┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐
│ Context │───▶│  Node1  │───▶│  Node2  │───▶│  Node3  │───▶ Result
└─────────┘    └─────────┘    └─────────┘    └─────────┘
     │              │              │              │
     └──────────────┴──────────────┴──────────────┘
                   Context передаётся
                   между всеми нодами
```

---

## Context — шина данных

Context — это словарь, который передаётся между всеми нодами в пайплайне.

### Создание Context

```python
from ai_flow_engine import Context

# Пустой контекст
context = Context()

# С начальными данными
context = Context(data={
    "user_input": "Привет",
    "config": {"language": "ru"}
})

# С историей сообщений
context = Context(
    data={"user_input": "Как дела?"},
    history=[
        {"role": "user", "content": "Привет"},
        {"role": "assistant", "content": "Привет! Чем могу помочь?"}
    ]
)
```

### Работа с Context

```python
# Записать данные
context.set("key", "value")
context.set("result", {"data": 123})

# Прочитать данные
value = context.get("key")
result = context.get("result", default={})

# Обновить несколько значений
context.update({"key1": "value1", "key2": "value2"})

# Добавить в историю
context.add_to_history("user", "Новое сообщение")

# Преобразовать в словарь
data = context.to_dict()

# Создать копию
copy = context.copy()
```

### Структура Context

```python
{
    "data": {           # Основные данные
        "user_input": "...",
        "llm_response": "...",
        ...
    },
    "history": [        # История сообщений
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "timestamp": "..."}
    ],
    "logs": [           # Логи выполнения
        {"node_name": "...", "status": "success", ...}
    ],
    "config": {},       # Конфигурация пайплайна
    "metadata": {       # Метаданные
        "pipeline_name": "...",
        "started_at": "...",
        "finished_at": "..."
    }
}
```

---

## Nodes — атомарные операции

### LLMNode

Выполняет запросы к LLM через OpenRouter.

```python
from ai_flow_engine.nodes import LLMNode

node = LLMNode(
    name="chat",
    model="openai/gpt-4o-mini",      # Модель
    prompt="Ты полезный ассистент",   # Системный промпт
    input_key="user_input",           # Ключ для чтения из Context
    output_key="llm_response",        # Ключ для записи в Context
    temperature=0.7,                  # Температура
    max_tokens=1024,                  # Макс. токенов
    include_history=True,             # Включать историю
    streaming=False                   # Режим стриминга
)
```

### PromptNode

Шаблоны промптов с Jinja2.

```python
from ai_flow_engine.nodes import PromptNode

node = PromptNode(
    name="prepare_prompt",
    template="Анализируй текст: {{ text }}. Фокус: {{ focus }}",
    variables={"text": "user_input", "focus": "analysis_focus"},
    output_key="prompt"
)
```

### ConditionNode

Условное ветвление.

```python
from ai_flow_engine.nodes import ConditionNode

node = ConditionNode(
    name="check_sentiment",
    condition={"key": "sentiment", "operator": "==", "value": "positive"},
    on_true="positive_handler",    # Имя следующей ноды
    on_false="negative_handler"
)

# Операторы: ==, !=, >, <, contains, exists, empty, starts_with
```

### WebSearchNode

Веб-поиск.

```python
from ai_flow_engine.nodes import WebSearchNode

node = WebSearchNode(
    name="search",
    query="последние новости AI",  # или "$user_input" для чтения из Context
    max_results=5,
    provider="duckduckgo",         # или "serpapi"
    output_key="search_results"
)
```

### ImageAnalysisNode

Анализ изображений через Vision модели.

```python
from ai_flow_engine.nodes import ImageAnalysisNode

node = ImageAnalysisNode(
    name="analyze_image",
    model="google/gemini-3-flash-preview",
    prompt="Опиши что изображено на картинке",
    image_path="path/to/image.jpg",  # или image_url="https://..."
    output_key="image_analysis"
)
```

---

## Pipeline — пайплайн

### Создание пайплайна

```python
from ai_flow_engine.core.engine import Pipeline
from ai_flow_engine.nodes import LLMNode, PromptNode

# Из списка нод
pipeline = Pipeline(
    nodes=[
        PromptNode(name="prompt", template="...", output_key="prompt"),
        LLMNode(name="llm", input_key="prompt", output_key="response")
    ],
    name="my_pipeline"
)

# Или просто списком
pipeline = [
    PromptNode(...),
    LLMNode(...)
]
```

### Выполнение пайплайна

```python
from ai_flow_engine import PipelineRunner, Context

runner = PipelineRunner(
    stop_on_error=True,  # Остановить при ошибке
    max_steps=100         # Макс. шагов (защита от циклов)
)

# Синхронное выполнение
result = await runner.execute(pipeline, context)

# Со стримингом
async for context in runner.stream(pipeline, context):
    print(context.get("llm_response"))
```

---

## Конфигурация пайплайнов

### JSON формат

```json
{
  "name": "vacancy_analyzer",
  "description": "Анализ вакансий",
  "version": "1.0.0",
  "nodes": [
    {
      "type": "WebSearchNode",
      "name": "search",
      "config": {
        "query": "data scientist вакансии",
        "max_results": 10
      }
    },
    {
      "type": "PromptNode",
      "name": "prepare_prompt",
      "config": {
        "template": "Извлеки навыки из вакансий: {{ search_results }}",
        "output_key": "analysis_prompt"
      }
    },
    {
      "type": "LLMNode",
      "name": "analyze",
      "config": {
        "model": "openai/gpt-4o-mini",
        "input_key": "analysis_prompt",
        "output_key": "skills"
      }
    }
  ]
}
```

### Загрузка конфигурации

```python
from ai_flow_engine.config import PipelineLoader, load_pipeline_from_file

# Загрузить из файла
pipeline = load_pipeline_from_file("pipelines/analyzer.json")

# Или через Loader
loader = PipelineLoader()
pipeline = loader.load_from_yaml("pipelines/analyzer.yaml")

# Загрузить все пайплайны из директории
pipelines = loader.load_from_directory("pipelines/")
```

---

## API Reference

### REST API Endpoints

#### POST /execute

Выполнить пайплайн.

```bash
curl -X POST http://localhost:8000/execute \
  -H "Content-Type: application/json" \
  -d '{
    "pipeline_name": "simple_chat",
    "input_data": {"user_input": "Привет!"}
  }'
```

#### POST /chat

Простой чат с LLM.

```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Расскажи шутку",
    "model": "openai/gpt-4o-mini"
  }'
```

#### POST /chat/stream

Чат со стримингом (Server-Sent Events).

```javascript
const eventSource = new EventSource('/chat/stream');
eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.chunk);  // Текст по кусочкам
};
```

---

## Примеры использования

### Пример 1: Простой чат-бот

```python
import asyncio
from ai_flow_engine import Context, PipelineRunner
from ai_flow_engine.nodes import LLMNode

async def chat():
    llm = LLMNode(
        model="openai/gpt-4o-mini",
        prompt="Ты дружелюбный ассистент",
        include_history=True
    )
    
    runner = PipelineRunner()
    context = Context()
    
    while True:
        user_input = input("Вы: ")
        if user_input == "exit":
            break
        
        context.set("user_input", user_input)
        context = await runner.execute([llm], context)
        
        print(f"AI: {context.get('llm_response')}")
    
    runner = PipelineRunner()
    context = Context()
    
    print("Калькулятор выражений. Введите 'exit' для выхода.")
    
    while True:
        user_input = input("Выражение: ")
        if user_input == "exit":
            break
        
        context.set("user_input", user_input)
        context = await runner.execute([llm], context)
        
        print(f"Ответ: {context.get('llm_response')}")
    
    runner = PipelineRunner()
    context = Context()
    
    print("Сентимент-анализ. Введите текст (или 'exit'):")
    
    while True:
        user_input = input("Текст: ")
        if user_input == "exit":
            break
        
        # Запускаем анализ
        context.set("user_input", user_input)
        result = await runner.execute(pipeline, context)
        
        print(f"Сентимент: {result.get('sentiment')}")
        print(f"Ответ: {result.get('final_response')}")
        print()

asyncio.run(sentiment_chat())
```

---

## Отладка

### Debugger

```python
from ai_flow_engine import Debugger

# После выполнения пайплайна
debugger = Debugger(context)

# Вывести сводку
print(debugger.print_summary())

# Найти ошибки
failed = debugger.get_failed_nodes()

# Время выполнения
times = debugger.get_execution_times()

# Найти медленные ноды
slow = debugger.find_slow_nodes(threshold=1.0)

# Экспортировать логи
debugger.export_logs("debug.json")
```

### Быстрая отладка

```python
from ai_flow_engine.core.debugger import print_debug

# Сразу после выполнения
print(print_debug(context))
```

### Пример вывода

```
============================================================
PIPELINE EXECUTION SUMMARY
============================================================
Pipeline: my_pipeline
Status: success
Steps: 3
Started: 2026-03-16T12:00:00
Finished: 2026-03-16T12:00:05

DATA KEYS:
  ['user_input', 'prompt', 'llm_response']

EXECUTION LOG:
  ✓ prompt: success (0.05s)
  ✓ llm: success (4.2s)
  ✓ output: success (0.01s)
============================================================
```

---

## Заключение

AI Backend Framework предоставляет гибкий и расширяемый фундамент для создания AI-приложений. Используйте готовые ноды или создавайте свои для решения специфических задач.

Для получения дополнительной помощи обратитесь к исходному коду в репозитории или создайте issue на GitHub.