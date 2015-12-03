################################################################
# xmldirector.crex
# (C) 2015,  Andreas Jung, www.zopyx.com, Tuebingen, Germany
################################################################


import os
import tempfile
from xmldirector.crex.browser import api

from Products.Five.browser import BrowserView


class Demo(BrowserView):

    def convert(self):

        zip_tmp = tempfile.mktemp(suffix='.zip')
        with open(zip_tmp, 'wb') as fp:
            fp.write(self.request.form['zipfile'].read())
        zip_out = api.convert_crex(zip_tmp)
        with open(zip_out, 'rb') as fp:
            self.request.response.setHeader('content-type', 'application/zip')
            self.request.response.setHeader('content-disposition', 'attachment;filename={}'.format('c-rex-converted.zip'))
            self.request.response.setHeader('content-length', str(os.path.getsize(zip_out)))
            self.request.response.write(fp.read())
