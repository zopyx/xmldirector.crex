
import pprint
import json
import requests
from requests.auth import HTTPBasicAuth


def verify_result(result):
    data_json = result.json()
    if 'error' in data_json:
        print result.url
        print data_json['error']
        raise RuntimeError()

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

print '-'*80
print 'SEARCH'
result = requests.get(url + '/@@API/xmldirector/search', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
verify_result(result)
data = result.json()
pprint.pprint(data)

print '-'*80
print 'CREATE'
result = requests.post(url + '/@@API/xmldirector/create', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
verify_result(result)
print result
data = result.json()
id = data['id']
url = data['url']
print(id)
print (url)

print '-'*80
print 'GET_METADATA'
result = requests.get(url + '/@@API/xmldirector/get_metadata/', auth=HTTPBasicAuth(user, password), data=json.dumps(payload))
verify_result(result)
data = result.json()
pprint.pprint(data)


print '-'*80
print 'SET_METADATA'
payload = dict(
    title=u'new title: hello world',
    description=u'New description'
)
result = requests.post(url + '/@@API/xmldirector/set_metadata', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
verify_result(result)
print result


print '-'*80
print 'GET_METADATA'
result = requests.get(url + '/@@API/xmldirector/get_metadata/', auth=HTTPBasicAuth(user, password), data=json.dumps(payload))
verify_result(result)
data = result.json()
pprint.pprint(data)

for i in range(1,3):
    print '-'*80
    print 'UPLOAD DOCX'
    files = {'file': open('sample.docx', 'rb')}
    print url
    result = requests.post(url + '/@@API/xmldirector/store', auth=HTTPBasicAuth(user, password), files=files)
    verify_result(result)
    data = result.json()
    pprint.pprint(data)

print '-'*80
print 'UPLOAD GET'
print url
result = requests.get(url + '/@@API/xmldirector/get', auth=HTTPBasicAuth(user, password))
verify_result(result)
data = result.json()
pprint.pprint(data)

print '-'*80
print 'CONVERT2'
result = requests.get(url + '/@@API/xmldirector/convert2/', auth=HTTPBasicAuth(user, password))
verify_result(result)
data = result.json()
pprint.pprint(data)

#print '-'*80
#print 'CONVERT'
#files = {'file': open('sample.zip', 'rb')}
#result = requests.post(url + '/@@API/xmldirector/convert/', auth=HTTPBasicAuth(user, password), files=files)
#verify_result(result)
#data = result.json()
#pprint.pprint(data)


print '-'*80
print 'DELETE'
result = requests.get(url + '/@@API/xmldirector/delete/', auth=HTTPBasicAuth(user, password), headers=headers,data=json.dumps(payload))
verify_result(result)
data = result.json()
pprint.pprint(data)

