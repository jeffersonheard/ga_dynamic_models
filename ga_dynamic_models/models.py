# IAH! IAH!
# Hastur, Hastur, Hastur!
"""
This module is insane.  What it does, effectively, is construct Models from objects  listed in a MongoDB database.
Quite a lot of functionality you'd expect could only be achieved through actual physical declaration of a class can be
done here.

A few meta-"types" we'll define here.  A callable is represented in JSON as::

    { 'type' : 'callable',
      'module' : fully_qualified_module_name,
      'callable' : name of the callable in question - cannot be dotted,
      'parameters' : list of JSON types or callables.  Callables will be called from the inside out
    }

A module-level attribute is represented as::

    { 'type' : 'attribute',
      'module' : ...,
      'attribute' : attribute name
    }

A class level attribute is represented as::

    { 'type' : 'class_attribute',
      'module' : ...,
      'cls' : ...,
      'attribute' : name
    }

A class level method is represented as::

    { 'type' : 'class_method',
      'module' : ...,
      'cls' : ...,
      'method' : name
      'parameters' : { 'positionals' : list of JSON types or callables.  Callables will be called from the inside out,
                       'keywords' : same }
    }


A date is represented as any valid date string from ga_ows.utils.parsetime like this::

    { 'type' : 'datetime',
      'value' : timestring
    }

In principle, there are model mixins, multiple inheritance, custom field types, all of that. In practice that won't
happen, likely, but why not support it?

A model can be constructed from a dictionary modeled on the following structure::

    {
      'name' : string,
      'bases' : [ attribute<model_subclass>, ... ],
      'fields' : {
            field_name : { callable<field_subclass>, ...
      },
      'meta' : {
          'abstract' : boolean,
          'app_label' : string<app name>,
          'db_table' : string<table name>,
          'db_tablespace' : string<tablespace name>,
          'get_latest_by' : string<field name>,
          'managed' : boolean<managed by django>,
          'order_with_respect_to' : string<foreign key field name>
      },      
    }
    
Additionally, look for how to expose modules in wms/wfs in ows.py and in Tastypie in api.py.
"""

from django.conf import settings
from django.db import models
from django.db.models.base import ModelBase
import importlib
from logging import getLogger
import ga_ows.utils
from pprint import pprint

def print_locals(fun):
    def wrapper(**kwargs):
        print fun.__name__
        pprint(kwargs)
        return fun(**kwargs)
    return wrapper

def print_imports(fun):
    global _imports
    def wrapper(kwargs):
        ret = fun(kwargs)
        print fun.__name__
        for k, v in _imports.items():
            print (k, v.__name__)
        return ret
    return wrapper

@print_imports
def _ensure_import(module):
    global _imports
    if module not in _imports:
        _imports[module] = importlib.import_module(module)        
    return _imports[module]

def _parse_item(item):
    ret = item
    if isinstance(item, dict):
        t = item['type']
        if t == 'callable':
            ret = _parse_callable(**t)
        elif t == 'attribute':
            ret = _parse_attribute(**t)
        elif t == 'class_attribute':
            ret = _parse_class_attribute(**t)
        elif t == 'class_method':
            ret = _parse_class_method(**t)
        elif t == 'datetime':
            ret = ga_ows.utils.parsetime(item['value'])
    else:
        try:
            ret = int(item) # correct for the fact that JSON doesn't differentiate between ints and floats
        except ValueError:
            pass
    return ret

def _parse_positionals(parameters):
    if 'positionals' in parameters:
        return [_parse_item(it) for it in parameters['positionals']]
    else:
        return []

def _parse_keywords(parameters):
    if 'keywords' in parameters:
        return dict([(key, _parse_item(value)) for key, value in parameters['keywords'].items()])
    else:
        return {}

def _parse_bases(bases):
    return tuple([_parse_attribute(**base) for base in bases])


def _parse_callable(type, module, callable, parameters):
    m=_ensure_import(module)
    return m.__getattribute__(callable)(*_parse_positionals(parameters), **_parse_keywords(parameters))

def _parse_attribute(type, module, attribute):
    m=_ensure_import(module)
    return m.__getattribute__(attribute)

def _parse_class_attribute(type, module, cls, attribute):
    m=_ensure_import(module)
    c = m.__getattribute__(cls)
    return c.__getattribute__(attribute)

def _parse_class_method(type, module, cls, method, parameters):
    m=_ensure_import(module)
    m.__getattribute__(cls).__getattribute__(method)(*_parse_positionals(parameters), **_parse_keywords(parameters))

def _parse_meta(**kwds):
    return type("Meta", (object,), kwds)

def _parse_model(name, bases, fields, meta, **kwargs):
    name = name.encode('ascii')
    fs =  dict([(n.encode('ascii'), _parse_callable(**f)) for n, f in fields.items()])
    fs['Meta'] = _parse_meta(**meta)
    fs['__metaclass__'] = ModelBase
    fs['__module__'] = __name__

    return type(name, _parse_bases(bases), fs)

if not hasattr(settings, "MONGODB_ROUTES"):
    raise AttributeError('MONGODB_ROUTES must be filled in')

_log = getLogger(__name__)

if 'ga_dynamic_models' in settings.MONGODB_ROUTES:
    _db = settings.MONGODB_ROUTES['ga_dynamic_models']
else:
    _db = settings.MONGODB_ROUTES['default']

_coll = _db['ga_dynamic_models__models']
_dynamic_models = _coll.find()

_imports = {
    'django.db.models' : importlib.import_module('django.db.models'),
    'django.contrib.gis.db.models' : importlib.import_module('django.contrib.gis.db.models')
}

__all__ = []

g = globals()
for model in _dynamic_models:
    g[model['name']] = _parse_model(**model)
    __all__.append(model['name'])


