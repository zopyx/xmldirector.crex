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
import datetime
import tempfile
import requests

import plone.api
from zope.component import getUtility
from zope.annotation.interfaces import IAnnotations
from AccessControl import Unauthorized
from AccessControl import getSecurityManager
from plone.registry.interfaces import IRegistry
from plone.jsonapi.core import router

from xmldirector.crex.logger import LOG
from xmldirector.crex.interfaces import ICRexSettings

from xmldirector.plonecore.browser.connector import Connector as connector_view

from zopyx.plone.persistentlogger.logger import IPersistentLogger


ANNOTATION_KEY = 'xmldirector.plonecore.crex'

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

@router.add_route("/xmldirector/convert", "convert", methods=["POST"])
def convert(context, request):

    if not getSecurityManager().checkPermission("Modify Portal Content", context):
        raise Unauthorized("You don't have the 'Modify Portal Content' permission")

    zip_tmp = tempfile.mktemp(suffix='.zip')
    with open(zip_tmp, 'wb') as fp:
        fp.write(request.form['file'].read())
        
    zip_out = convert_crex(zip_tmp)
    with open(zip_out, 'rb') as fp:
        return dict(data=json.dumps(fp))
#    from ZPublisher.Iterators import filestream_iterator
#    request.response.setHeader('content-type', 'application/zip')
#    request.response.setHeader('content-length', str(os.path.getsize(zip_out)))
#    return filestream_iterator(zip_out)

@router.add_route("/xmldirector/search", "search", methods=["GET"])
def search(context, request):

    if not getSecurityManager().checkPermission("View", context):
        raise Unauthorized("You don't have the 'View' permission")

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


@router.add_route("/xmldirector/export-zip", "export-zip", methods=["GET"])
def export_zip(context, request):
    
    if not getSecurityManager().checkPermission("View", context):
        raise Unauthorized("You don't have the 'View' permission")

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


@router.add_route("/xmldirector/delete", "delete", methods=["GET"])
def delete(context, request):

    if not getSecurityManager().checkPermission("Manage Delete", context):
        raise Unauthorized("You don't have the 'Manage Delete' permission")

    parent = context.aq_parent
    parent.manage_delObjects(context.getId())
    return dict()

@router.add_route("/xmldirector/get_metadata", "get_metadata", methods=["GET"])
def get_metadata(context, request):

    if not getSecurityManager().checkPermission("View", context):
        raise Unauthorized("You don't have the 'View' permission")

    annotations = IAnnotations(context)
    custom = annotations.get(ANNOTATION_KEY)

    return dict(
        id=context.getId(),
        title=context.Title(),
        description=context.Description(),
        created=context.created().ISO8601(),
        modified=context.modified().ISO8601(),
        subject=context.Subject(),
        creator=context.Creator(),
        custom=custom)

@router.add_route("/xmldirector/create", "create", methods=["POST"])
def create(context, request):

    if not getSecurityManager().checkPermission("Modify Portal Content", context):
        raise Unauthorized("You don't have the 'Modify Portal Content' permission")

    payload = json.loads(request.BODY)
    id = str(uuid.uuid4())
    title = payload.get('title')
    description = payload.get('description')
    custom = payload.get('custom')

    connector = plone.api.content.create(type='xmldirector.plonecore.connector',
        container=context,
        id=id,
        title=title,
        description=description)

    if custom:
        annotations = IAnnotations(connector)
        annotations[ANNOTATION_KEY] = custom

    IPersistentLogger(connector).log('created', details=payload)
    return dict(
        id=id,
        url=connector.absolute_url(),
        )

@router.add_route("/xmldirector/set_metadata", "set_metadat", methods=["POST"])
def set_metadata(context, request):

    if not getSecurityManager().checkPermission("Modify Portal Content", context):
        raise Unauthorized("You don't have the 'Modify Portal Content' permission")

    payload = json.loads(request.BODY)

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
