# -*- coding: utf-8 -*-

################################################################
# xmldirector.crex
# (C) 2015,  Andreas Jung, www.zopyx.com, Tuebingen, Germany
################################################################


import os
import json
import time
import furl
import uuid
import hashlib
import datetime
import tempfile
import requests
import fnmatch
import fs.zipfs

import plone.api
from zope import interface
from zope.component import getUtility
from zope.annotation.interfaces import IAnnotations
from Products.CMFCore import permissions
from AccessControl import Unauthorized
from AccessControl import getSecurityManager
from plone.registry.interfaces import IRegistry
from plone.jsonapi.core import router
from plone.jsonapi.core.interfaces import IRouteProvider

from plone.rest import Service

from xmldirector.crex.logger import LOG
from xmldirector.crex.interfaces import ICRexSettings

from xmldirector.plonecore.browser.connector import Connector as connector_view
from xmldirector.plonecore.interfaces import IWebdavHandle

from zopyx.plone.persistentlogger.logger import IPersistentLogger


ANNOTATION_KEY = 'xmldirector.plonecore.crex'


class CRexConversionError(Exception):
    """ A generic C-Rex error """


def check_permission(permission, context):
    """ Check the given Zope permission against a context object """

    if not getSecurityManager().checkPermission(permission, context):
        raise Unauthorized('You don\'t have the \'{}\' permission'.format(permission))


def decode_json_payload(request):
    """ Extract JSON data from the body of a Zope request """

    body = getattr(request, 'BODY', None)
    if not body:
        raise ValueError(u'Request does not contain body data')

    try:
        return json.loads(body)
    except ValueError:
        raise ValueError(u'Request body could not be decoded as JSON')


def sha256_fp(fp, blocksize=2**20):
    """ Calculate SHA256 hash for an open file(handle) """

    fp.seek(0)
    sha256 = hashlib.sha256()
    while True:
        data = fp.read(blocksize)
        if not data:
            break
        sha256.update(data)
    return sha256.hexdigest()


def store_zip(context, zip_filename, target_directory):
    """ Unzip a ZIP file within the given target directory """

    handle = context.webdav_handle()
    if handle.exists(target_directory):
        handle.removedir(target_directory, recursive=True, force=True)
    handle.makedir(target_directory)
    with fs.zipfs.ZipFS(zip_filename, 'r') as zip_in:
        for name in zip_in.walkfiles():
            target_path = '{}/{}'.format(target_directory, name.replace('/result/', ''))
            target_dir = os.path.dirname(target_path)
            if not handle.exists(target_dir):
                handle.makedir(target_dir, recursive=True)
            with handle.open(target_path, 'wb') as fp_out:
                with zip_in.open(name, 'rb') as fp_in:
                    fp_out.write(fp_in.read())


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



def timed(method):
    """ A timing decorator """

    def timed(self):
        path = self.context.absolute_url(1)
        ts = time.time()
        result = method(self)
        te = time.time()
        s = u'{:>25}(\'{}\')'.format(self.__class__.__name__, path)
        s = s + u': {:2.6f} seconds'.format(te-ts)
        LOG.info(s)
        return result
    return timed


class BaseService(Service):
    """ Base class for REST services """

    @property
    def catalog(self):
        return plone.api.portal.get_tool('portal_catalog')


class api_create(BaseService):

    @timed
    def render(self):
        """ Create a new content object in Plone """

        check_permission(permissions.ModifyPortalContent, self.context)
        payload = decode_json_payload(self.request)

        id = str(uuid.uuid4())
        title = payload.get('title')
        description = payload.get('description')
        custom = payload.get('custom')

        connector = plone.api.content.create(type='xmldirector.plonecore.connector',
            container=self.context,
            id=id,
            title=title,
            description=description)

        connector.webdav_subpath = 'plone-api-{}/{}'.format(plone.api.portal.get().getId(), id)
        handle = connector.webdav_handle(create_if_not_existing=True)

        if custom:
            annotations = IAnnotations(connector)
            annotations[ANNOTATION_KEY] = custom

        IPersistentLogger(connector).log('created', details=payload)
        self.request.response.setStatus(201)
        return dict(
            id=id,
            url=connector.absolute_url(),
            )


class api_search(BaseService):

    @timed
    def render(self):

        check_permission(permissions.View, self.context)

        catalog = plone.api.portal.get_tool('portal_catalog')
        query = dict(portal_type='xmldirector.plonecore.connector', path='/'.join(self.context.getPhysicalPath()))
        brains = catalog(**query)
        items = list()
        for brain in brains:
            items.append(dict(
                id=brain.getId,
                path=brain.getPath(),
                url=brain.getURL(),
                title=brain.Title,
                creator=brain.Creator,
                created=brain.created.ISO8601(),
                modified=brain.modified.ISO8601()))
        return dict(items=items)


class api_get_metadata(BaseService):

    @timed
    def render(self):

        check_permission(permissions.View, self.context)

        annotations = IAnnotations(self.context)
        custom = annotations.get(ANNOTATION_KEY)

        return dict(
            id=self.context.getId(),
            title=self.context.Title(),
            description=self.context.Description(),
            created=self.context.created().ISO8601(),
            modified=self.context.modified().ISO8601(),
            subject=self.context.Subject(),
            creator=self.context.Creator(),
            custom=custom)


class api_set_metadata(BaseService):

    @timed
    def render(self):

        check_permission(permissions.ModifyPortalContent, self.context)

        payload = decode_json_payload(self.request)
        IPersistentLogger(self.context).log('set_metadata', details=payload)

        title = payload.get('title')
        if title:
            self.context.setTitle(title)

        description = payload.get('description')
        if description:
            self.context.setDescription(description)
        
        subject = payload.get('subject')
        if subject:
            self.context.setSubject(subject)

        custom = payload.get('custom')
        if custom:
            annotations = IAnnotations(self.context)
            annotations[ANNOTATION_KEY] = custom

        return dict()


class api_delete(BaseService):

    @timed
    def render(self):

        check_permission(permissions.DeleteObjects, self.context)

        util = getUtility(IWebdavHandle)

        handle = util.webdav_handle()
        handle.removedir(self.context.webdav_subpath, True, True)

        parent = self.context.aq_parent
        parent.manage_delObjects(self.context.getId())
        return dict()


class api_store(BaseService):

    @timed
    def render(self):
        
        check_permission(permissions.ModifyPortalContent, self.context)
        IPersistentLogger(self.context).log('store')
        payload = decode_json_payload(self.request)
        webdav_handle = self.context.webdav_handle()

        target_dir = 'src'
        if webdav_handle.exists(target_dir):
            webdav_handle.removedir(target_dir, force=True)
        webdav_handle.makedir(target_dir)

        # Write payload/data to ZIP file
        zip_out = tempfile.mktemp(suffix='.zip')
        with open(zip_out, 'wb') as fp:
            fp.write(payload['zip'].decode('base64'))

        # and unpack it        
        with fs.zipfs.ZipFS(zip_out, 'r') as zip_handle:
            for name in zip_handle.walkfiles():
                dest_name = '{}/{}'.format(target_dir, name)
                dest_dir = os.path.dirname(dest_name)
                if not webdav_handle.exists(dest_dir):
                    webdav_handle.makedir(dest_dir)
                data = zip_handle.open(name, 'rb').read()
                with webdav_handle.open(dest_name, 'wb') as fp:
                    fp.write(data)
                with webdav_handle.open(dest_name + '.sha256', 'wb') as fp:
                    fp.write(hashlib.sha256(data).hexdigest())
        return dict(msg=u'Saved')


class api_get(BaseService):

    @timed
    def render(self):

        check_permission(permissions.ModifyPortalContent, self.context)
        json_data = decode_json_payload(self.request)

        if not 'files' in json_data:
            raise ValueError(u'JSON structure has no \'files\' field')

        files = json_data['files']

        handle = self.context.webdav_handle()
        zip_out = tempfile.mktemp(suffix='.zip')
        with fs.zipfs.ZipFS(zip_out, 'w') as zip_handle:
            for name in handle.walkfiles():
                if name.startswith('/'):
                    name = name[1:]
                for fname in files:
                    if fnmatch.fnmatch(name, fname):
                        with handle.open(name, 'rb') as fp_in:
                            with zip_handle.open(name, 'wb') as fp_out:
                                fp_out.write(fp_in.read())
                        break

        with open(zip_out, 'rb') as fp:
            return dict(file=fp.read().encode('base64'))


class api_convert(BaseService):

    @timed
    def render(self):

        check_permission(permissions.ModifyPortalContent, self.context)
        IPersistentLogger(self.context).log('convert')

        handle = self.context.webdav_handle()
        zip_tmp = tempfile.mktemp(suffix='.zip')
        with fs.zipfs.ZipFS(zip_tmp, 'w') as zip_fp:
            with zip_fp.open('word/index.docx', 'wb') as fp:
                with handle.open('src/word/index.docx', 'rb') as fp_in:
                    fp.write(fp_in.read())

        zip_out = convert_crex(zip_tmp)
        store_zip(self.context, zip_out, 'current')

        with open(zip_out, 'rb') as fp:
            return dict(data=fp.read().encode('base64'))


class api_list(BaseService):

    @timed
    def render(self):

        check_permission(permissions.View, self.context)

        handle = self.context.webdav_handle()
        return dict(files=list(handle.walkfiles()))
