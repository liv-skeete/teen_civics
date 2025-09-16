import os
from requests_oauthlib import OAuth1Session
from src.load_env import load_env

load_env()

api_key = os.getenv('TWITTER_API_KEY')
api_secret = os.getenv('TWITTER_API_SECRET')
access_token = os.getenv('TWITTER_ACCESS_TOKEN')
access_secret = os.getenv('TWITTER_ACCESS_SECRET')

# Create an OAuth1 session
twitter = OAuth1Session(api_key,
                        client_secret=api_secret,
                        resource_owner_key=access_token,
                        resource_owner_secret=access_secret)

# Make a request to the verify_credentials endpoint
url = 'https://api.twitter.com/1.1/account/verify_credentials.json'
response = twitter.get(url)

print(response.status_code)
print(response.json())