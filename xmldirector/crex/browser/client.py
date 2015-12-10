import json
import requests

url = 'http://dev1.veit-schiele.de:12020/Plone/test'
headers = {
    'content-type': 'application/json'
}
data = json.dumps(dict(hello='world'))
print requests.patch(url, headers=headers, data=data)
print requests.get(url, headers=headers, data=data)
print requests.put(url, headers=headers, data=data)
print requests.post(url, headers=headers, data=data)
