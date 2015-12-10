import json
import requests

url = 'http://dev1.veit-schiele.de:12020/Plone/test'
headers = {
    'content-type': 'application/json',
    'Accept': 'application/json'
}

data = json.dumps(dict(hello='world'))
#print requests.patch(url, headers=headers, data=data)
#print requests.get(url, headers=headers, data=data)
#print requests.put(url, headers=headers, data=data)
print requests.post(url, headers=headers, data=data)

print requests.put(url + '/xxx', headers=headers, data=data)
print requests.put(url + '/xxx/xxx', headers=headers, data=data)
result = requests.get(url + '/get-download', headers=headers, data=data)
print result
open('out.zip', 'wb').write(result.content)

files = dict(file=open('out.zip', 'rb'))
result = requests.post(url + '/post-upload', headers=headers, files=files)
print result


