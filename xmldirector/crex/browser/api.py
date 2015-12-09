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

    def timed(self, context, request):
        path = context.absolute_url(1)
        ts = time.time()
        result = method(self, context, request)
        te = time.time()
        s = u'{}(\'{}\'): {:2.6f} seconds'.format(method.__name__, path, te-ts)
        LOG.info(s)
        return result
    return timed


class APIRoutes(object):
    interface.implements(IRouteProvider)

    def initialize(self, context, request):
        self.request = request
        self.context = context

    @property
    def routes(self):
        return [
            ('/xmldirector/get', 'xmldirector/get', self.api_get,  dict(methods=['POST'])),
            ('/xmldirector/store', 'xmldirector/store', self.api_store, dict(methods=['POST'])),
            ('/xmldirector/convert2', 'xmldirector/convert2', self.api_convert2, dict(methods=['GET'])),
            ('/xmldirector/convert', 'xmldirector/convert', self.api_convert, dict(methods=['POST'])),
            ('/xmldirector/search', 'xmldirector/search', self.api_search, dict(methods=['GET'])),
            ('/xmldirector/export-zip', 'xmldirector/export-zip', self.api_export_zip, dict(methods=['GET'])),
            ('/xmldirector/delete', 'xmldirector/delete', self.api_delete, dict(methods=['GET'])),
            ('/xmldirector/get_metadata', 'xmldirector/get_metadata', self.api_get_metadata, dict(methods=['GET'])),
            ('/xmldirector/create', 'xmldirector/create', self.api_create, dict(methods=['POST'])),
            ('/xmldirector/set_metadata', 'xmldirector/set_metadata', self.api_set_metadata, dict(methods=['POST'])),
        ]


    @timed
    def api_get(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        json_data = decode_json_payload(request)

        if not 'files' in json_data:
            raise ValueError(u'JSON structure has no \'files\' field')

        files = json_data['files']

        handle = context.webdav_handle()
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


    @timed
    def api_store(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        IPersistentLogger(context).log('store')

        original_fn = os.path.basename(request.form['file'].filename)

        out_tmp = tempfile.mktemp(suffix=original_fn)
        with open(out_tmp, 'wb') as fp:
            fp.write(request.form['file'].read())

        sha256 = hashlib.sha256()
        with open(out_tmp, 'rb') as fp:
            sha256_digest = sha256_fp(fp)

        handle = context.webdav_handle()
        target_path = 'word/index.docx'
        if not handle.exists(os.path.dirname(target_path)):
            handle.makedir(os.path.dirname(target_path))

        existing_sha256 = None
        if handle.exists(target_path + '.sha256'):
            with handle.open(target_path + '.sha256', 'rb') as fp:
                existing_sha256 = fp.read()

        if existing_sha256 != sha256_digest:
            with open(out_tmp, 'rb') as fp_out:
                with handle.open(target_path, 'wb') as fp_in:
                    fp_in.write(fp_out.read())
                with handle.open(target_path + '.sha256', 'wb') as sha_fp:
                    sha_fp.write(sha256_digest)
                
            return dict(msg=u'Saved')
        else:
            return dict(msg=u'Not saved, no modifications')
        

    @timed
    def api_convert2(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        IPersistentLogger(context).log('convert2')

        handle = context.webdav_handle()
        zip_tmp = tempfile.mktemp(suffix='.zip')
        with fs.zipfs.ZipFS(zip_tmp, 'w') as zip_fp:
            with zip_fp.open('word/index.docx', 'wb') as fp:
                with handle.open('word/index.docx', 'rb') as fp_in:
                    fp.write(fp_in.read())
                
            
        zip_out = convert_crex(zip_tmp)
        store_zip(context, zip_out, 'current')

        with open(zip_out, 'rb') as fp:
            return dict(data=fp.read().encode('base64'))

    @timed
    def api_convert(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        IPersistentLogger(context).log('convert')

        zip_tmp = tempfile.mktemp(suffix='.zip')
        with open(zip_tmp, 'wb') as fp:
            fp.write(request.form['file'].read())
            
        zip_out = convert_crex(zip_tmp)
        store_zip(context, zip_out, 'current')

        with open(zip_out, 'rb') as fp:
            return dict(data=fp.read().encode('base64'))

    @timed
    def api_search(self, context, request):

        check_permission(permissions.View, context)

        catalog = plone.api.portal.get_tool('portal_catalog')
        query = dict(portal_type='xmldirector.plonecore.connector')
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

    @timed
    def api_export_zip(self, context, request):
        
        check_permission(permissions.View, context)

        path = request.form.get('path')
        if not path:
            raise ValueError('``path`` parameter missing')

        obj = context.restrictedTraverse(path, None)
        if obj is None:
            raise ValueError('Unable to retrieve object ({})'.format(path))

        dirs = request.form.get('dirs', '')

        view = connector_view(request=request, context=context)
        view.zip_export(dirs=dirs, download=True)
        self.request.response.setStatus(200)
        self.request.response.write('DONE')


    @timed
    def api_delete(self, context, request):

        check_permission(permissions.DeleteObjects, context)

        util = getUtility(IWebdavHandle)

        handle = util.webdav_handle()
        handle.removedir(context.webdav_subpath, True, True)

        parent = context.aq_parent
        parent.manage_delObjects(context.getId())
        return dict()

    @timed
    def api_get_metadata(self, context, request):

        check_permission(permissions.View, context)

        annotations = IAnnotations(context)
        custom = annotations.get(ANNOTATION_KEY)

        _api = list()
        for item in self.routes:
            url = '{}/@@API/{}'.format(context.absolute_url(), item[0])
            methods = item[-1]['methods']
            doc = item[2].__doc__
            name = item[0]
            _api.append(dict(
                url=url,
                methods=methods,
                doc=doc,
                name=name))

        return dict(
            id=context.getId(),
            title=context.Title(),
            description=context.Description(),
            created=context.created().ISO8601(),
            modified=context.modified().ISO8601(),
            subject=context.Subject(),
            creator=context.Creator(),
            custom=custom,
            _api=_api)

    @timed
    def api_create(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        payload = decode_json_payload(request)

        id = str(uuid.uuid4())
        title = payload.get('title')
        description = payload.get('description')
        custom = payload.get('custom')

        connector = plone.api.content.create(type='xmldirector.plonecore.connector',
            container=context,
            id=id,
            title=title,
            description=description)

        connector.webdav_subpath = 'plone-api-{}/{}'.format(plone.api.portal.get().getId(), id)
        handle = connector.webdav_handle(create_if_not_existing=True)

        if custom:
            annotations = IAnnotations(connector)
            annotations[ANNOTATION_KEY] = custom

        IPersistentLogger(connector).log('created', details=payload)
        request.response.setStatus(201)
        return dict(
            id=id,
            url=connector.absolute_url(),
            )

    @timed
    def api_set_metadata(self, context, request):

        check_permission(permissions.ModifyPortalContent, context)
        payload = decode_json_payload(request)
        IPersistentLogger(context).log('set_metadata', details=payload)

        title = payload.get('title')
        if title:
            context.setTitle(title)

        description = payload.get('description')
        if description:
            context.setDescription(description)
        
        subject = payload.get('subject')
        if subject:
            context.setSubject(subject)

        custom = payload.get('custom')
        if custom:
            annotations = IAnnotations(context)
            annotations[ANNOTATION_KEY] = custom

        return dict()
