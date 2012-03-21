"""
Utilities for creating dynamic models.

Usage is similar to this::

    mymodel = simple_geomodel("MyModel", managed=False, db_table='my_model',
        mychar = simple_geofield("CharField", max_length=255, default=''),
        mygeom = simple_geofield("PolygonField", srid=3157, null=True),
        ...
    )

    declare_model(mymodel)
"""
from django.conf import settings
import importlib
import sys
from datetime import datetime
from django.core.management import call_command
from django.db import connection, transaction

def method(method, *parameters):
    return {
        'method' : method,
        'parameters' : parameters
    }

def queryset(module, model, *extra):
    return {
        "type" : "queryset",
        "module" : module,
        "model" : model,
        "extra" : extra
    }

def attribs(module, *ls):
    return {
        "type" : 'attribs',
        "module" : module,
        "ls" : ls
    }

def callable(module, name, *args, **kwargs):
    return {
        "type" : "callable",
        "module" : module,
        "callable" : name,
        "parameters" : { "positionals" : args, "keywords" : kwargs }
    }

def attribute(module, name):
    return {
        "type" : "attribute",
        "module" : module,
        "attribute" : name
    }

def class_attribute(module, cls, attribute):
    return {
        "type" : "class_attribute",
        "module" : module,
        "cls" : cls,
        "attribute" : attribute
    }

def class_method(module, cls, method, *args, **kwargs):
    return {
        "type" : "class_method",
        "module" : module,
        "cls" : cls,
        "method" : method,
        "parameters" : { "positionals" : args, "keywords" : kwargs }
    }

def model(name, bases, fields, **meta):
    for key, value in meta.items():
        if value is None:
            del meta[key]

    if not isinstance(bases, list):
        bases = [bases]

    return {
        "name" : name,
        "bases" : bases,
        "fields" : fields,
        "meta" : meta
    }

def resource(name, bases, fields, **meta):
    for key, value in meta.items():
        if value is None:
            del meta[key]

    if not isinstance(bases, list):
        bases = [bases]

    return {
        "name" : name,
        "bases" : bases,
        "fields" : fields,
        "meta" : meta
    }

def simple_model_resource(module, model, resource_name, **meta):
    meta['queryset'] = queryset(module, model, method('all', []))
    meta['resource_name'] = resource_name

    return resource(model, attribute('tastypie.resources', 'ModelResource'), {}, **meta)

def simple_geo_resource(module, model, resource_name, **meta):
    meta['queryset'] = queryset(module, model, method('all', []))
    meta['resource_name'] = resource_name

    return resource(model, attribute('ga_ows.tastyhacks', 'GeoResource'), {}, **meta)

def simple_geomodel(name, managed=True, db_table=None, **fields):
    fields['objects'] = callable("django.contrib.gis.db.models", "GeoManager")
    return model(
        name,
        attribute('django.contrib.gis.db.models', 'Model'),
        fields,
        managed=managed,
        db_table=db_table,
        app_label='ga_dynamic_models'
    )

def simple_model(name, managed=True, db_table=None, **fields):
    return model(
        name,
        attribute('django.db.models', 'Model'),
        fields,
        managed=managed,
        db_table=db_table,
        app_label='ga_dynamic_models'
    )

def simple_field(kind, *args, **kwargs):
    return {
        "type" : "callable",
        "module" : 'django.db.models',
        "callable" : kind,
        "parameters" : { 'positionals' : args, 'keywords' : kwargs }
    }

def simple_geofield(kind, *args, **kwargs):
    return {
        "type" : "callable",
        "module" : 'django.contrib.gis.db.models',
        "callable" : kind,
        "parameters" : { 'positionals' : args, 'keywords' : kwargs }
    }

def declare_model(model, replace=False, user=None, syncdb=False):
    model['_id'] = model['name']

    _db = get_connection()

    if user:
        model['_owner'] = user.pk
    else:
        model['_owner'] = None

    one = _db['ga_dynamic_models__models'].find_one(model['name'], fields=['_id', '_owner'])
    print "found old model"
    if not one:
        _db['ga_dynamic_models__models'].insert(model, safe=True)
    elif replace and ((not one['owner']) or user.pk == one['owner']):
        _db['ga_dynamic_models__models'].save(model, safe=True)
    else:
        raise Exception("Cannot insert model record")

    print "inserted new model"
    print "syncdb"
    if syncdb:
        m = get_model(model['name'])


        call_command('syncdb', interactive=False)
    print "syncdb finished"

    declare_updated()

def drop_resource(model, user=None):
    _db = get_connection()

    if isinstance(model, str) or isinstance(model, unicode):
        one = _db['ga_dynamic_models__api'].find_one(model, fields=['_id', '_owner'])
    else:
        one = _db['ga_dynamic_models__api'].find_one(model['name'], fields=['_id', '_owner'])

    if one:
        if '_owner' not in one or not one['_owner'] or one['_owner'] == user.pk:
            _db['ga_dynamic_models__api'].remove(model)
        else:
            raise Exception("Cannot delete resource record")
    declare_updated()


def declare_resource(model, replace=False, user=None):
    model['_id'] = model['name']

    _db = get_connection()

    if user:
        model['_owner'] = user.pk
    else:
        model['_owner'] = None

    one = _db['ga_dynamic_models__api'].find_one(model['name'], fields=['_id', '_owner'])
    if not one:
        _db['ga_dynamic_models__api'].insert(model, safe=True)
    elif replace and ((not one['_owner']) or user.pk == one['_owner']):
        _db['ga_dynamic_models__api'].save(model, safe=True)
    else:
        raise Exception("Cannot insert resource record")

    declare_updated()

def drop_model(model, user=None):
    _db = get_connection()

    one = _db['ga_dynamic_models__models'].find_one(model, fields=['_id', 'owner'])

    if one:
        if '_owner' not in one or not one['_owner'] or one['_owner'] == user.pk:
            try:
                m = get_model(model)
                cursor = connection.cursor()
                cursor.execute("DROP TABLE " + m._meta.db_table)
                transaction.commit_unless_managed()
                print "deleted table"
                _db['ga_dynamic_models__models'].remove(model)
            except AttributeError:
                pass
        else:
            raise Exception("Cannot delete model record")
        declare_updated()
        call_command('syncdb', interactive=False)

def get_connection():
    if 'ga_dynamic_models' in settings.MONGODB_ROUTES:
        _db = settings.MONGODB_ROUTES['ga_dynamic_models']
    else:
        _db = settings.MONGODB_ROUTES['default']
    return _db

def get_model(model):
    try:
        del sys.modules['ga_dynamic_models.models']
    except KeyError:
        pass

    models = importlib.import_module('ga_dynamic_models.models')
    if hasattr(models, model):
        return models.__getattribute__(model)
    else:
        raise AttributeError("No such model")

def declare_updated():
    db = get_connection()
    one = db['ga_dynamic_models__aux'].find_one()
    if not one:
        db['ga_dynamic_models__aux'].save({
            "update_time" : datetime.utcnow()
        }, safe=True)

def reload_if_updated(mytime, name):
    fresh = get_connection()['ga_dynamic_models__aux'].find_one()
    if not fresh:
        declare_updated()
        fresh = get_connection()['ga_dynamic_models__aux'].find_one()
    if mytime < fresh['update_time']:
        del sys.modules[name]
        importlib.import_module(name)
        return True
    else:
        return False




