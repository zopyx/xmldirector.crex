# -*- coding: utf-8 -*-

################################################################
# xmldirector.crex
# (C) 2015,  Andreas Jung, www.zopyx.com, Tuebingen, Germany
################################################################


import os
import tempfile
from xmldirector.crex.browser import service

from Products.Five.browser import BrowserView


class Converter(BrowserView):
    """ C-Rex converter """

    def convert(self):
        """ Convert uploaded ZIP file ``zipfile`` using C-Rex """

        zf = self.request.form.get('zipfile')
        if not zf:
            raise ValueError('No  ZIP file uploaded?')

        zip_tmp = tempfile.mktemp(suffix='.zip')
        basename = os.path.basename(zf.filename)
        basename, ext = os.path.splitext(basename)
        with open(zip_tmp, 'wb') as fp:
            fp.write(zf.read())
        zip_out = service.convert_crex(zip_tmp)
        with open(zip_out, 'rb') as fp:
            self.request.response.setHeader('content-type', 'application/zip')
            self.request.response.setHeader(
                'content-disposition', 'attachment;filename={}'.format('{}-converted.zip'.format(basename)))
            self.request.response.setHeader(
                'content-length', str(os.path.getsize(zip_out)))
            self.request.response.write(fp.read())
