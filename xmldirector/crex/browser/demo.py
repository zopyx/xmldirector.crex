################################################################
# xmldirector.crex
# (C) 2015,  Andreas Jung, www.zopyx.com, Tuebingen, Germany
################################################################


import os
from xmldirector.crex.browser import api

from Products.Five.browser import BrowserView


class Demo(BrowserView):

    def demo(self):
        zip_file = os.path.join(os.path.dirname(__file__), 'data', 'sample.zip')
        result = api.convert_crex(zip_file)
        return result
