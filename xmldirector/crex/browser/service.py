from plone.rest import Service

class Patch(Service):

    def render(self):
        print 'xx'
        return {'message': 'PATCH: Hello World!'}
