from dotenv import load_dotenv
import os
import openai

load_dotenv()

client = openai.OpenAI(
    api_key=os.getenv("YANDEX_API_KEY"),
    base_url=os.getenv("YANDEX_BASE_URL"),
    project=os.getenv("YANDEX_FOLDER_ID"),
)

response = client.chat.completions.create(
    model=os.getenv("YANDEX_MODEL_URI"),
    messages=[{"role": "user", "content": "Ответь одним словом: тест пройден."}],
    temperature=float(os.getenv("YANDEX_TEMPERATURE", "0.4")),
    max_tokens=int(os.getenv("YANDEX_MAX_TOKENS", "10000")),
)

print(response.choices[0].message.content)
