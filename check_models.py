import requests

API_KEY = 'AIzaSyCzZHRlsnsC1AFmny_V_YoTLgmjOnH8k2s'
url = f'https://generativelanguage.googleapis.com/v1beta/models?key={API_KEY}'
response = requests.get(url)
print('Status:', response.status_code)
if response.status_code == 200:
    data = response.json()
    print('Available models:')
    for model in data.get('models', [])[:10]:
        name = model.get('name', '')
        if 'gemini' in name.lower():
            print(f'  - {name}')
else:
    print('Error:', response.text[:200])