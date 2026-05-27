import requests
import json

url = 'https://v3.football.api-sports.io/fixtures'
params = {'league': 39, 'season': 2024}
headers = {
    'x-rapidapi-key': '42ce6ecab1ca5f63aff02cabca89298c',
    'x-rapidapi-host': 'v3.football.api-sports.io'
}

response = requests.get(url, params=params, headers=headers)
print(json.dumps(response.json(), indent=2))
