import asyncio
import aiohttp

async def test():
    url = 'https://api.perplexity.ai/chat/completions'
    payload = {
        'model': 'sonar-pro',
        'messages': [
            {'role': 'system', 'content': 'Du bist Research-Assistent.'},
            {'role': 'user', 'content': 'Wie viel Protein enthält Käse pro 100g?'}
        ],
        'max_tokens': 800,
        'temperature': 0.1,
        'return_citations': True
    }
    import os

    headers = {
        'Authorization': f'Bearer {os.getenv("PERPLEXITY_API_KEY")}',
        'Content-Type': 'application/json'
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as resp:
            print(f'Status: {resp.status}')
            text = await resp.text()
            print(f'Response:\n{text}')

asyncio.run(test())
