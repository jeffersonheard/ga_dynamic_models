"""
Note this module is mostly copied wholesale from models.py.  It was done so because I wasn't sure how much code I could
share between them.  As it looks like practically all the code is shared between them now, it would make sense to make
one "parser.py" module and work from there.
"""

from tastypie.api import Api
from tastypie.resources import ModelDeclarativeMetaclass
from django.conf import settings
from ga_dynamic_models.parser import Parser
from logging import getLogger

if not hasattr(settings, "MONGODB_ROUTES"):
    raise AttributeError('MONGODB_ROUTES must be filled in')

_log = getLogger(__name__)

if 'ga_dynamic_models' in settings.MONGODB_ROUTES:
    _db = settings.MONGODB_ROUTES['ga_dynamic_models']
else:
    _db = settings.MONGODB_ROUTES['default']

_coll = _db['ga_dynamic_models__api']
_dynamic_model_resources = _coll.find()

__all__ = []

api = Api('ga_dynamic_models')
g = globals()
p = Parser(__name__, ModelDeclarativeMetaclass)
for res in _dynamic_model_resources:
    try:
        cls = p.parse(**res)
        g[res['name']] = cls
        __all__.append(res['name'])
        api.register(cls())
    except Exception as e:
        _log.error('Trouble creating resource {res}'.format(res=res), str(e))
