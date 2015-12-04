# -*- coding: utf-8 -*-

################################################################
# xmldirector.crex
# (C) 2015,  Andreas Jung, www.zopyx.com, Tuebingen, Germany
################################################################


import os
import time
import furl
import datetime
import tempfile
import requests

import plone.api
from zope.component import getUtility
from plone.registry.interfaces import IRegistry

from xmldirector.crex.logger import LOG
from xmldirector.crex.interfaces import ICRexSettings


class CRexConversionError(Exception):
    pass


def convert_crex(zip_path):
    """ Send ZIP archive with content to be converted to C-Rex.
        Returns name of ZIP file with converted resources.
    """


    ts = time.time()
    registry = getUtility(IRegistry)
    settings = registry.forInterface(ICRexSettings)

    # Fetch authentication token if necessary (older than one hour)
    crex_token = settings.crex_conversion_token
    crex_token_last_fetched = settings.crex_conversion_token_last_fetched or datetime.datetime(
        2000, 1, 1)
    diff = datetime.datetime.utcnow() - crex_token_last_fetched
    if not crex_token or diff.total_seconds() > 3600:
        f = furl.furl(settings.crex_conversion_url)
        token_url = '{}://{}/api/Token'.format(f.scheme, f.host, settings.crex_conversion_url)
        headers = {'content-type': 'application/x-www-form-urlencoded'}
        params = dict(
            username=settings.crex_conversion_username,
            password=settings.crex_conversion_password,
            grant_type='password')
        result = requests.post(token_url, data=params, headers=headers)
        if result.status_code != 200:
            msg = u'Error retrieving DOCX conversion token from webservice (HTTP code {}, Message {})'.format(
                result.status_code, result.text)
            LOG.error(msg)
            raise CRexConversionError(msg)
        data = result.json()
        crex_token = data['access_token']
        settings.crex_conversion_token = crex_token
        settings.crex_conversion_token_last_fetched = datetime.datetime.utcnow()
        LOG.info('Fetching new DOCX authentication token - successful')
    else:
        LOG.info('Fetching DOCX authentication token from Plone cache')

    headers = {'authorization': 'Bearer {}'.format(crex_token)}

    with open(zip_path, 'rb') as fp:
        try:
            LOG.info(u'Starting C-Rex conversion of {}, size {} '.format(zip_path, os.path.getsize(zip_path)))
            result = requests.post(
                settings.crex_conversion_url, files=dict(source=fp), headers=headers)
        except requests.ConnectionError:
            msg = u'Connection to C-REX webservice failed'
            raise CRexConversionError(msg)

        if result.status_code == 200:
            msg = u'Conversion successful (HTTP code {}, duration: {:2.1f} seconds))'.format(result.status_code, time.time() - ts)
            LOG.info(msg)
            zip_out = tempfile.mktemp(suffix='.zip')
            with open(zip_out, 'wb') as fp:
                fp.write(result.content)
            return zip_out

        else:
            # Forbidden -> invalid token -> invalidate token stored in Plone
            if result.status_code == 401:
                settings.crex_conversion_token = u''
                settings.crex_conversion_token_last_fetched = datetime.datetime(
                    1999, 1, 1)
            msg = u'Conversion failed (HTTP code {}, message {})'.format(
                result.status_code, result.text)
            LOG.error(msg)
            raise CRexConversionError(msg)
