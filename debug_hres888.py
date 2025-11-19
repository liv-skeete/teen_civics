import os
import requests
import json
from src.load_env import load_env

load_env()
api_key = os.getenv('CONGRESS_API_KEY')

if not api_key:
    print("API Key not found")
    exit(1)

url = "https://api.congress.gov/v3/bill/119/hres/888?format=json&api_key=" + api_key
response = requests.get(url)
print(json.dumps(response.json(), indent=2))
