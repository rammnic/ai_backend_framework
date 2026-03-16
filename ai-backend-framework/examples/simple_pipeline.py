"""
Simple pipeline example - Basic LLM chat
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from ai_flow_engine import Context, PipelineRunner
from ai_flow_engine.nodes import LLMNode, PromptNode


async def simple_chat():
    """Simple chat example"""
    print("=== Simple Chat Example ===\n")
    
    # Create pipeline nodes
    pipeline = [
        LLMNode(
            name="chat",
            model="openai/gpt-4o-mini",
            prompt="Ты полезный ИИ-ассистент. Отвечай кратко и по делу.",
            include_history=True,
        )
    ]
    
    # Create runner and context
    runner = PipelineRunner()
    context = Context()
    
    print("Чат с AI. Напишите 'exit' для выхода.\n")
    
    while True:
        user_input = input("Вы: ")
        if user_input.lower() == "exit":
            break
        
        context.set("user_input", user_input)
        context = await runner.execute(pipeline, context)
        
        print(f"AI: {context.get('llm_response')}\n")


async def prompt_template_example():
    """Example with prompt templates"""
    print("=== Prompt Template Example ===\n")
    
    pipeline = [
        PromptNode(
            name="prepare_prompt",
            template="Объясни простыми словами, что такое {{ topic }}. Используй примеры.",
            variables={"topic": "user_input"},
            output_key="prompt"
        ),
        LLMNode(
            name="explain",
            model="openai/gpt-4o-mini",
            input_key="prompt",
            output_key="explanation"
        )
    ]
    
    runner = PipelineRunner()
    context = Context(data={"user_input": "квантовые вычисления"})
    
    result = await runner.execute(pipeline, context)
    
    print(f"Тема: {context.get('user_input')}")
    print(f"Объяснение: {result.get('explanation')}")


async def streaming_example():
    """Example with streaming response"""
    print("=== Streaming Example ===\n")
    
    llm = LLMNode(
        name="streaming_chat",
        model="openai/gpt-4o-mini",
        streaming=True,
    )
    
    context = Context(data={"user_input": "Напиши короткое стихотворение о программировании"})
    
    print("AI: ", end="", flush=True)
    
    async for updated_context in llm.stream(context):
        chunk = updated_context.get("_streaming_chunk", "")
        if chunk:
            print(chunk, end="", flush=True)
    
    print("\n")


async def main():
    """Run all examples"""
    
    # Check for API key
    if not os.getenv("OPENROUTER_API_KEY"):
        print("Ошибка: Установите OPENROUTER_API_KEY в .env файле")
        print("Скопируйте .env.example в .env и добавьте ключ")
        return
    
    # Run examples
    await prompt_template_example()
    print("\n" + "=" * 50 + "\n")
    
    await streaming_example()
    print("\n" + "=" * 50 + "\n")
    
    # Interactive chat (uncomment to try)
    await simple_chat()


if __name__ == "__main__":
    asyncio.run(main())