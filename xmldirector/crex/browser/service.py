import json
from plone.rest import Service

class Patch(Service):

    def render(self):
        print '-'*80
        print self.request.REQUEST_METHOD
        print self.request.form
        print json.loads(self.request.BODY)
        return {'message': 'PATCH: Hello World!'}

class Patch2(Service):

    def render(self):
        print '*'*80
        print self.request.REQUEST_METHOD
        print self.request.form
        print json.loads(self.request.BODY)
        return {'message': 'PATCH2: Hello World!'}

class GET(Service):

    def render(self):
        self.request.response.setHeader('content-type', 'application/zip')
        with open('/tmp/sample.zip', 'rb') as fp:
            self.request.response.write(fp.read())

class POST(Service):

    def render(self):
        return {'message': 'PATCH2: Hello World!'}
