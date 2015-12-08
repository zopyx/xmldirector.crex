
import pprint
import json
import requests
from requests.auth import HTTPBasicAuth

url = 'http://dev1.veit-schiele.de:12020/Plone'
user = 'admin'
password = 'admin'

headers = {'content-type': 'application/json'}
payload = dict(
    title=u'Hello world',
    description=u'This is the description',
    custom=dict(
        a=1,
        b=2,
        hello=u'world')
)

result = requests.post(url + '/@@API/xmldirector/create', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
data = result.json()
id = data['id']
url = data['url']
print(id)
print (url)

result = requests.get(url + '/@@API/xmldirector/get_metadata/', auth=HTTPBasicAuth(user, password), data=json.dumps(payload))
data = result.json()
pprint.pprint(data)


payload = dict(
    title=u'new title: hello world',
    description=u'New description'
)
result = requests.post(url + '/@@API/xmldirector/set_metadata', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
print result


result = requests.get(url + '/@@API/xmldirector/get_metadata/', auth=HTTPBasicAuth(user, password), data=json.dumps(payload))
data = result.json()
pprint.pprint(data)


files = {'file': open('sample.zip', 'rb')}
result = requests.post(url + '/@@API/xmldirector/convert/', auth=HTTPBasicAuth(user, password), files=files)
data = result.json()
pprint.pprint(data)



#result = requests.get(url + '/@@API/xmldirector/delete/', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
#data = result.json()
#pprint.pprint(data)

print url
