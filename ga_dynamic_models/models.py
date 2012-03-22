# IAH! IAH!
# Hastur, Hastur, Hastur!
"""
This module is insane.  What it does, effectively, is construct Models from objects  listed in a MongoDB database.
Quite a lot of functionality you'd expect could only be achieved through actual physical declaration of a class can be
done here.  One thing that's essential right now, thoguh is that the WSGI container **must** be restarted after a model
is declared.  There's probably a way around it, but right now I don't know it.  A task for doing this, if you're using
this with Geoanalytics, is declared in tasks.py and can be called via Celery's task mechanism.

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
from django.db.models.base import ModelBase
from logging import getLogger
from ga_dynamic_models.parser import Parser


if not hasattr(settings, "MONGODB_ROUTES"):
    raise AttributeError('MONGODB_ROUTES must be filled in')

_log = getLogger(__name__)

if 'ga_dynamic_models' in settings.MONGODB_ROUTES:
    _db = settings.MONGODB_ROUTES['ga_dynamic_models']
else:
    _db = settings.MONGODB_ROUTES['default']

_coll = _db['ga_dynamic_models__models']
_dynamic_models = _coll.find()

__all__ = []

g = globals()
p = Parser(__name__, ModelBase)
for model in _dynamic_models:
    try:
        g[model['name']] = p.parse(**model)
        __all__.append(model['name'])
    except Exception as e:
        _log.error("Error creating {model}".format(model=model), str(e))
        print e

