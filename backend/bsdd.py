"""Public versioned bSDD reads and optional project property reference schemas."""
import json
import copy
import time
from collections import OrderedDict
from threading import RLock
from urllib.parse import unquote, urlsplit

import httpx
from fastapi import Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from backend.providers import ProviderError

API = "https://api.bsdd.buildingsmart.org"
USER_AGENT = "ORBIT/0.6.0"
# Only anonymous, public metadata is shared. Never cache customer data or errors.
_CACHE = OrderedDict()
_CACHE_LOCK = RLock()
_CACHE_SECONDS = 300



def identifier(value, kind="dictionary"):
    """Identifiers are query values, never outbound request destinations."""
    try:
        url = urlsplit(value)
        if url.scheme != "https" or url.netloc != "identifier.buildingsmart.org" or url.query or url.fragment or len(value) > 1000 or any(c.isspace() for c in value):
            raise ValueError()
        parts = url.path.rstrip('/').split('/')
        if parts[:2] != ['', 'uri'] or len(parts) < 5:
            raise ValueError()
        if kind == 'dictionary' and len(parts) != 5:
            raise ValueError()
        if kind == 'class' and (len(parts) != 7 or parts[5] != 'class'):
            raise ValueError()
        if any(not p or unquote(p) in {'.', '..'} or any(c in unquote(p) for c in '/\\\r\n\t') for p in parts[2:]):
            raise ValueError()
    except ValueError:
        raise ProviderError("invalid_identifier", "Use a versioned bSDD identifier URL, such as https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3")
    return value.rstrip('/')


def fetch(path, params, transport=None):
    if path not in {'/api/Dictionary/v1', '/api/Dictionary/v1/Classes', '/api/Class/v1'}:
        raise ValueError('Unsupported bSDD operation')
    key = (path, tuple(sorted(params.items())))
    if transport is None:
        with _CACHE_LOCK:
            cached = _CACHE.get(key)
            if cached and cached[0] > time.monotonic():
                _CACHE.move_to_end(key)
                return copy.deepcopy(cached[1])
    try:
        with httpx.Client(transport=transport, timeout=httpx.Timeout(20, connect=5), follow_redirects=False, trust_env=True) as client:
            with client.stream('GET', API + path, params=params, headers={'Accept': 'application/json', 'User-Agent': USER_AGENT}) as response:
                if response.status_code == 429:
                    raise ProviderError('rate_limited', 'bSDD rate limit reached. Try again later.')
                if response.status_code in {401, 403}:
                    raise ProviderError('access_denied', 'This bSDD resource is not publicly accessible. Private dictionary authentication is not configured.')
                if response.status_code != 200:
                    raise ProviderError('bsdd_unavailable', 'bSDD did not return a successful response. Check the identifier and try again.')
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 2_000_000:
                        raise ProviderError('response_too_large', 'bSDD response exceeds the bounded lookup limit.')
                    chunks.append(chunk)
                payload = json.loads(b''.join(chunks))
                if not isinstance(payload, dict):
                    raise ValueError()
                if transport is None:
                    with _CACHE_LOCK:
                        _CACHE[key] = (time.monotonic() + _CACHE_SECONDS, copy.deepcopy(payload))
                        _CACHE.move_to_end(key)
                        while len(_CACHE) > 64:
                            _CACHE.popitem(last=False)
                return payload
    except (httpx.HTTPError, ValueError):
        raise ProviderError('bsdd_read_failed', 'Could not read bSDD. Check network access and retry; the saved project selection is unchanged.')


def text(row, key, required=False, maximum=1000):
    value = row.get(key, '')
    if value is None and not required:
        return ''
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ProviderError('contract_mismatch', 'bSDD returned an unexpected field format.')
    return value


def dictionary(row):
    if not isinstance(row, dict):
        raise ProviderError('contract_mismatch', 'bSDD returned an unexpected dictionary.')
    return {'uri': identifier(text(row, 'uri', True)), **{key: text(row, key, key in {'name', 'version'}) for key in ['name', 'version', 'code', 'organizationNameOwner', 'status', 'license', 'licenseUrl']}}


def dictionaries(offset=0, uri='', transport=None):
    params = {'Uri': identifier(uri)} if uri else {'Offset': offset, 'Limit': 25}
    data = fetch('/api/Dictionary/v1', params, transport)
    rows = data.get('dictionaries')
    if not isinstance(rows, list) or len(rows) > 25:
        raise ProviderError('contract_mismatch', 'bSDD returned an unexpected dictionary list.')
    for key in ['offset', 'count', 'totalCount']:
        if type(data.get(key)) is not int or data[key] < 0:
            raise ProviderError('contract_mismatch', 'bSDD returned unexpected dictionary paging information.')
    if data['count'] != len(rows) or data['offset'] != (0 if uri else offset):
        raise ProviderError('contract_mismatch', 'bSDD returned inconsistent dictionary paging information.')
    result = {'dictionaries': [dictionary(row) for row in rows], 'offset': data['offset'], 'count': data['count'], 'total': data['totalCount']}
    if uri and (len(rows) != 1 or result['dictionaries'][0]['uri'] != identifier(uri)):
        raise ProviderError('dictionary_not_found', 'That exact dictionary version was not returned by bSDD.')
    return result


def classes(uri, offset=0, transport=None):
    uri = identifier(uri)
    data = fetch('/api/Dictionary/v1/Classes', {'Uri': uri, 'Offset': offset, 'Limit': 25}, transport)
    if data.get('uri') != uri or not isinstance(data.get('classes'), list) or len(data['classes']) > 25:
        raise ProviderError('contract_mismatch', 'bSDD class results did not match the selected dictionary.')
    for key in ['classesOffset', 'classesCount', 'classesTotalCount']:
        if type(data.get(key)) is not int or data[key] < 0:
            raise ProviderError('contract_mismatch', 'bSDD returned unexpected class paging information.')
    if data['classesOffset'] != offset or data['classesCount'] != len(data['classes']):
        raise ProviderError('contract_mismatch', 'bSDD returned inconsistent class paging information.')
    result = []
    for row in data['classes']:
        if not isinstance(row, dict):
            raise ProviderError('contract_mismatch', 'bSDD returned an unexpected class.')
        class_uri = identifier(text(row, 'uri', True), 'class')
        if class_uri.rsplit('/class/', 1)[0] != uri:
            raise ProviderError('scope_mismatch', 'bSDD returned a class outside the selected dictionary.')
        result.append({'uri': class_uri, 'name': text(row, 'name', True), 'code': text(row, 'code')})
    return {'classes': result, 'offset': offset, 'count': len(result), 'total': data['classesTotalCount']}


def class_details(dictionary_uri, class_uri, transport=None):
    dictionary_uri, class_uri = identifier(dictionary_uri), identifier(class_uri, 'class')
    if class_uri.rsplit('/class/', 1)[0] != dictionary_uri:
        raise ProviderError('scope_mismatch', 'Choose a class from the selected dictionary version.')
    data = fetch('/api/Class/v1', {'Uri': class_uri, 'IncludeClassProperties': 'true'}, transport)
    if data.get('uri') != class_uri or data.get('dictionaryUri') != dictionary_uri or not isinstance(data.get('classProperties'), list) or len(data['classProperties']) > 500:
        raise ProviderError('contract_mismatch', 'bSDD returned an unexpected class/property contract.')
    properties, seen = [], set()
    for row in data['classProperties']:
        if not isinstance(row, dict):
            raise ProviderError('contract_mismatch', 'bSDD returned an unexpected property.')
        uri = identifier(text(row, 'uri', True), 'property')
        if uri in seen:
            raise ProviderError('contract_mismatch', 'bSDD returned duplicate class-property identifiers.')
        seen.add(uri)
        property_uri = identifier(text(row, 'propertyUri', True), 'property')
        value = {'uri': uri, 'propertyUri': property_uri, **{key: text(row, key, key == 'name', 10000 if key in {'definition', 'description'} else 1000) for key in ['name', 'propertyCode', 'propertySet', 'dataType', 'definition', 'description', 'unit', 'propertyValueKind']}}
        # Do not turn buildingSMART optional metadata into project requirements.
        for key in ['allowedValues', 'units']:
            if key in row:
                if not isinstance(row[key], list) or len(row[key]) > 500:
                    raise ProviderError('contract_mismatch', 'bSDD returned unexpected property constraints.')
                value[key] = row[key]
        properties.append(value)
    return {'uri': class_uri, 'name': text(data, 'name', True), 'code': text(data, 'code'), 'properties': properties}


class Selection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: int = Field(ge=0)
    enabled: bool = False
    dictionary_uri: str = Field(default='', max_length=1000)
    class_uri: str = Field(default='', max_length=1000)
    property_uris: list[str] = Field(default_factory=list, max_length=100)


def register_bsdd(app, db, identity, permit, project_check, audit, now):
    def check(who, project, action='connection'):
        permit(who, action)
        with db() as c:
            project_check(c, who, project)

    def recheck(request, who, project):
        current = identity(request)
        if current['user_id'] != who['user_id'] or current['tenant_id'] != who['tenant_id']:
            raise HTTPException(409, 'Identity changed during bSDD lookup; reload and retry.')
        check(current, project)
        return current

    def provider_error(error):
        raise HTTPException(422 if error.code in {'invalid_identifier', 'scope_mismatch', 'dictionary_not_found'} else 502, {'code': error.code, 'message': error.message})

    def saved(c, who, project):
        return c.execute('SELECT * FROM bsdd_settings WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)).fetchone()

    @app.get('/api/projects/{project}/bsdd')
    def settings(project: str, who=Depends(identity)):
        check(who, project, 'view')
        with db() as c:
            row = saved(c, who, project)
        return {'version': row['version'] if row else 0, 'configuration': json.loads(row['configuration']) if row else {'enabled': False, 'dictionary': None, 'class': None, 'properties': []}, 'updated': row['updated'] if row else None, 'updated_by': row['updated_by'] if row else None}

    @app.get('/api/projects/{project}/bsdd/dictionaries')
    def list_dictionaries(project: str, request: Request, offset: int = Query(default=0, ge=0, le=100000), uri: str = Query(default='', max_length=1000), who=Depends(identity)):
        check(who, project)
        try:
            result = dictionaries(offset, uri)
        except ProviderError as error:
            provider_error(error)
        recheck(request, who, project)
        return {**result, 'observed': now(), 'api': API, 'authenticated': False}

    @app.get('/api/projects/{project}/bsdd/classes')
    def list_classes(project: str, request: Request, dictionary_uri: str = Query(max_length=1000), offset: int = Query(default=0, ge=0, le=100000), who=Depends(identity)):
        check(who, project)
        try:
            result = classes(dictionary_uri, offset)
        except ProviderError as error:
            provider_error(error)
        recheck(request, who, project)
        return result

    @app.get('/api/projects/{project}/bsdd/class')
    def get_class(project: str, request: Request, dictionary_uri: str = Query(max_length=1000), class_uri: str = Query(max_length=1000), who=Depends(identity)):
        check(who, project)
        try:
            result = class_details(dictionary_uri, class_uri)
        except ProviderError as error:
            provider_error(error)
        recheck(request, who, project)
        return result

    @app.put('/api/projects/{project}/bsdd')
    def save(project: str, request: Request, body: Selection, who=Depends(identity)):
        check(who, project)
        with db() as c:
            row = saved(c, who, project)
            if (row['version'] if row else 0) != body.version:
                raise HTTPException(409, 'Dictionary settings changed; reload before saving.')
        configuration = {'enabled': body.enabled, 'dictionary': None, 'class': None, 'properties': []}
        if body.property_uris and not body.class_uri or body.class_uri and not body.dictionary_uri or body.enabled and not body.dictionary_uri:
            raise HTTPException(422, 'Choose a dictionary before enabling it, and a class before selecting properties.')
        if len(set(body.property_uris)) != len(body.property_uris):
            raise HTTPException(422, 'Select each property once.')
        try:
            if body.dictionary_uri:
                configuration['dictionary'] = dictionaries(uri=body.dictionary_uri)['dictionaries'][0]
            if body.class_uri:
                detail = class_details(body.dictionary_uri, body.class_uri)
                configuration['class'] = {key: detail[key] for key in ['uri', 'name', 'code']}
                by_uri = {p['uri']: p for p in detail['properties']}
                if set(body.property_uris) - set(by_uri):
                    raise HTTPException(422, 'A selected property is no longer in this class. Reload the class and review it.')
                configuration['properties'] = [by_uri[uri] for uri in body.property_uris]
        except ProviderError as error:
            provider_error(error)
        current = recheck(request, who, project)
        stamp = now()
        configuration['verified_at'] = stamp if body.dictionary_uri else None
        with db() as c:
            project_check(c, current, project)
            if body.version == 0:
                # A concurrent first save must not overwrite another selection.
                c.execute('INSERT OR IGNORE INTO bsdd_settings VALUES(?,?,0,?,?,?)', (who['tenant_id'], project, '{}', stamp, who['user_id']))
            result = c.execute('UPDATE bsdd_settings SET version=version+1,configuration=?,updated=?,updated_by=? WHERE tenant_id=? AND project_id=? AND version=?', (json.dumps(configuration), stamp, current['user_id'], current['tenant_id'], project, body.version))
            if result.rowcount != 1:
                raise HTTPException(409, 'Dictionary settings changed; reload before saving.')
            audit(c, current, 'bsdd.selection_saved', project, f'version={body.version + 1};properties={len(configuration["properties"])}')
        return {'version': body.version + 1, 'configuration': configuration, 'updated': stamp, 'updated_by': current['user_id']}
