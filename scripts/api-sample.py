
import pprint
import json
import tempfile
import requests
import fs.zipfs
from requests.auth import HTTPBasicAuth


def verify_result(result):
    data_json = result.json()
    if 'error' in data_json:
        print result.url
        print data_json['error']
        raise RuntimeError()

base_url = 'http://dev1.veit-schiele.de:12020/Plone'
user = 'admin'
password = 'admin'
all_headers = {'content-type': 'application/json', 'accept' : 'application/json'}

def send_request(method='GET', path='/@@API', data=None, files=None, headers={}, folder=None, url=None):

    f = getattr(requests, method.lower())
    api_url = url if url else base_url
    if folder:
        api_url += folder
    api_url += '/{}'.format(path)
    request_headers = all_headers.copy()
    request_headers.update(headers)
    print method, api_url

    if files:
        zip_tmp = tempfile.mktemp(suffix='.zip')
        with fs.zipfs.ZipFS(zip_tmp, 'w') as handle:
            for fname in files:
                with open(fname, 'rb') as fp_in:
                    with handle.open(fname, 'wb') as fp_out:
                        fp_out.write(fp_in.read())
        data = json.dumps(dict(zip=open(zip_tmp, 'rb').read().encode('base64')))

    if data:
        result = f(
            api_url, 
            auth=HTTPBasicAuth(user, password),
            headers=request_headers,
            data=data)
    else:
        result = f(
            api_url, 
            auth=HTTPBasicAuth(user, password),
            headers=request_headers)
    print result
    return result


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
result = send_request('GET', 'xmldirector-search')
verify_result(result)
data = result.json()
pprint.pprint(data)

print '-'*80
print 'CREATE'
result = send_request('PUT', 'xmldirector-create', folder='/folder', data=json.dumps(payload))
verify_result(result)
print result
data = result.json()
id = data['id']
url = data['url']
print(id)
print (url)


print '-'*80
print 'GET_METADATA'
result = send_request('GET', 'xmldirector-get-metadata', url=url)
verify_result(result)
data = result.json()
pprint.pprint(data)


print '-'*80
print 'SET_METADATA'
payload = dict(
    title=u'new title: hello world',
    description=u'New description'
)
result = send_request('POST', 'xmldirector-set-metadata', data=json.dumps(payload), url=url)
verify_result(result)
print result

for i in range(1,3):
    print '-'*80
    print 'UPLOAD DOCX'
    files = ['word/index.docx']
    print url
    result = send_request('POST', 'xmldirector-store', files=files, url=url)
    verify_result(result)
    data = result.json()
    pprint.pprint(data)


print '-'*80
print 'GET'
payload = dict(
    files=['src/*']
)
result = send_request('POST', 'xmldirector-get', data=json.dumps(payload), url=url)
open('out.zip', 'wb').write(result.content)
print 'output written to out.zip'
#verify_result(result)

print '-'*80
print 'LIST'
result = send_request('GET', 'xmldirector-list', url=url)
verify_result(result)
data = result.json()
pprint.pprint(data)

print '-'*80
print 'LIST-FULL'
result = send_request('GET', 'xmldirector-list-full', url=url)
verify_result(result)
data = result.json()
pprint.pprint(data)


print '-'*80
print 'CONVERT'
result = send_request('GET', 'xmldirector-convert', url=url)
open('convert.zip', 'wb').write(result.content)
print 'conversion result written to convert.zip'


print '-'*80
print 'DELETE'
result = send_request('DELETE', 'xmldirector-delete', url=url)
verify_result(result)
data = result.json()
pprint.pprint(data)
