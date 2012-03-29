"""
Utilities for creating dynamic models.

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

Usage is similar to this::

    mymodel = simple_geomodel("MyModel", managed=False, db_table='my_model',
        mychar = simple_geofield("CharField", max_length=255, default=''),
        mygeom = simple_geofield("PolygonField", srid=3157, null=True),
        ...
    )

    declare_model(mymodel)

We refer to an **item** in this quite a lot.  An **item** is defined as anything that can be created by calling:

    * method
    * queryset
    * attribute
    * callable
    * class_method
    * class_attribute
    * attributes

or a bare string or number.  The caveat is that if you want a floating point number, you must have a decimal point, as
JSON doesn't distinguish between floats and integers.
"""
from django.conf import settings
import importlib
import sys
from datetime import datetime
from django.core.management import call_command
from django.db import connection, transaction

def method(method, *parameters):
    """
    Part of the grammar of dynamic models.  Declare a method.

    :param method: The name of the method
    :param parameters: A list of **item**s.
    :return: A JSON serializable dict.
    """
    return {
        'method' : method,
        'parameters' : parameters
    }

def queryset(module, model, *extra):
    """
    Part of the grammar of dynamic models.  A model queryset. Must be handled special because of the redefinition of __getattribute__ in ModelBase

    :param module: The dotted name of a module containing the model
    :param model: The classname of a model
    :param extra: Any **methods** that should be called to further winnow the queryset
    :return: A JSON serializable dict.
    """
    return {
        "type" : "queryset",
        "module" : module,
        "model" : model,
        "extra" : extra
    }

def attribs(module, *ls):
    """
    Part of the grammar of dynamic models.  A dotted chain of attributes.

    :param module: The dotted name of the module containing the attribute
    :param ls: The list of attribute names or **method**s to call to get the result desired
    :return: A JSON serializable dict
    """
    return {
        "type" : 'attribs',
        "module" : module,
        "ls" : ls
    }

def callable(module, name, *args, **kwargs):
    """
    Part of the grammar of dynamic models.  Call a python callable with arguments.

    :param module: The dotted name of the module containing the attribute.
    :param name: The name of the attribute.
    :param args: The positional arguments as **item**s to pass to the function call.
    :param kwargs: The keyword arguments as **item**s to pass to the function call
    :return: A JSON serializable dict
    """
    return {
        "type" : "callable",
        "module" : module,
        "callable" : name,
        "parameters" : { "positionals" : args, "keywords" : kwargs }
    }

def attribute(module, name):
    """
    Part of the grammar of dynamic models.  A single attribute of a module.

    :param module:  THe name of the module.
    :param name: The name of the attribute
    :return: A JSON serializable dict.
    """
    return {
        "type" : "attribute",
        "module" : module,
        "attribute" : name
    }

def class_attribute(module, cls, attribute):
    """
    Part of the grammar of dynamic models.  An attribute of a class

    :param module: The name of the module containing the class
    :param cls: The name of the class
    :param attribute: The name of the attribute
    :return: A JSON serializable dict
    """
    return {
        "type" : "class_attribute",
        "module" : module,
        "cls" : cls,
        "attribute" : attribute
    }

def class_method(module, cls, method, *args, **kwargs):
    """
    Part of the grammar of dynamic models.  A class method call

    :param module: The name of the module containing the class
    :param cls: The name of the class
    :param method: The name of the class method
    :param args: The arguments to pass as **item**s
    :param kwargs: The keyword arguments to pass as **item**s
    :return: A JSON serializable dict.
    """
    return {
        "type" : "class_method",
        "module" : module,
        "cls" : cls,
        "method" : method,
        "parameters" : { "positionals" : args, "keywords" : kwargs }
    }

def model(name, bases, fields, **meta):
    """
    Part of the grammar of dynamic models.  A model class declaration.  This function should encapsulate any model
    definition.

    :param name:  The name of the model to declare
    :param bases: The base classes of the model
    :param fields: The fields of the model as a dict of name => **field**
    :param meta: The metadata attributes of the model.  Keyword => **item**.
    :return:  A JSON serializable dict.
    """
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
    """
    Part of the grammar of dynamic models.  A TastyPie resource declaration.  This function should encapsulate
    any API declaration.

    :param name: The name of the resource to declare.
    :param bases: The base classes of the resource
    :param fields: The fields of the resource
    :param meta: The metadata attributes of the resource.
    :return: A JSON seralizable dict.
    """
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
    """
    A simplification for common TastyPie resource declarations.  Calls **resource** to declare a ModelResource.

    :param module: The name of the module the model is in.
    :param model: The model to make the API from.
    :param resource_name: The endpoint name of the resource.
    :param meta: The meta attributes of the resource.
    :return: A JSON serlizable dict.
    """

    meta['queryset'] = queryset(module, model, method('all', []))
    meta['resource_name'] = resource_name

    return resource(model, attribute('tastypie.resources', 'ModelResource'), {}, **meta)

def simple_geo_resource(module, model, resource_name, **meta):
    """
    Part of the grammar of dynamic models. A simplification for common TastyPie resource declarations.  Calls **resource**
    to declare a GeoModelResource (as defined in :py:mod:`ga_ows.tastyhacks` ).  A GeoResource sends GeoJSOn instead of
    JSON.

    :param module: The name of the module the model is in.
    :param model: The model to make the API from
    :param resource_name: The endpoint name of the resource
    :param meta: The meta attributes of the resource
    :return: A JSON serializable dict.
    """

    meta['queryset'] = queryset(module, model, method('all', []))
    meta['resource_name'] = resource_name

    return resource(model, attribute('ga_ows.tastyhacks', 'GeoResource'), {}, **meta)

def simple_geomodel(name, managed=True, db_table=None, **fields):
    """
    A simplification of the **model** function that declares a GeoDjango model.

    :param name: The name of the model
    :param managed: default True. The model's "managed" attribute.  See Django's model reference.
    :param db_table: The database table to point at.  Safe to leeave this as None unless you have a specific table.
    :param fields: The fields to put in the model, as keyword arguments. See **simple_field** or **simple_geofield**
    :return: A JSON Serializable dict.
    """
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
    """
    A simplification of the **model** function that declares a Django model.

    :param name: The name of the model
    :param managed: default True. The model's "managed" attribute.  See Django's model reference.
    :param db_table: The database table to point at.  Safe to leeave this as None unless you have a specific table.
    :param fields: The fields to put in the model, as keyword arguments. See **simple_field**.
    :return: A JSON Serializable dict.
    """
    return model(
        name,
        attribute('django.db.models', 'Model'),
        fields,
        managed=managed,
        db_table=db_table,
        app_label='ga_dynamic_models'
    )

def simple_field(kind, *args, **kwargs):
    """
    A simplification of the **callable* function that creates a field.

    :param kind:  The kind of field, should be in django.db.models.
    :param args: The positional arguments to the field as **item**s
    :param kwargs: The keyword arguments to the field as **item**s
    :return:
    """
    return {
        "type" : "callable",
        "module" : 'django.db.models',
        "callable" : kind,
        "parameters" : { 'positionals' : args, 'keywords' : kwargs }
    }

def simple_geofield(kind, *args, **kwargs):
    """
    A simplification of the **callable* function that creates a field.

    :param kind:  The kind of field, should be in django.contrib.gis.db.models.
    :param args: The positional arguments to the field as **item**s
    :param kwargs: The keyword arguments to the field as **item**s
    :return:
    """
    return {
        "type" : "callable",
        "module" : 'django.contrib.gis.db.models',
        "callable" : kind,
        "parameters" : { 'positionals' : args, 'keywords' : kwargs }
    }

def declare_model(model, replace=False, user=None, syncdb=False):
    """
    Adds the model to the database and calls syncdb.

    :param model: A model as defined by simple_model, simple_geomodel, or model.
    :param replace: Whether or not to replace the model if it already exists.
    :param user: The user who owns the model
    :param syncdb: Whether to call syncdb after the model is declared.
    :return: A JSON serializable dict.
    """
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

def drop_resource(resource, user=None):
    """
    Drops a TastyPie API resource from the DB, if it exists.

    :param resource: The resource name to drop.
    :param user: The user requesting the drop, if relevant.
    :return:
    """
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



def declare_resource(resource, replace=False, user=None):
    """
    Declares a TastyPie API and inserts it into the DB, if it exists.

    :param resource: The resource, as created by simple_model_resource, simple_geo_resource, etc.
    :param replace: Whether or not to replace the model if it already exists.
    :param user: The user who owns the resource
    :return:
    """
    resource['_id'] = resource['name']

    _db = get_connection()

    if user:
        resource['_owner'] = user.pk
    else:
        resource['_owner'] = None

    one = _db['ga_dynamic_models__api'].find_one(resource['name'], fields=['_id', '_owner'])
    if not one:
        _db['ga_dynamic_models__api'].insert(resource, safe=True)
    elif replace and ((not one['_owner']) or user.pk == one['_owner']):
        _db['ga_dynamic_models__api'].save(resource, safe=True)
    else:
        raise Exception("Cannot insert resource record")


def drop_model(model, user=None):
    """
    Drop a model from the database.  Drops the table as well.

    :param model: THe model name to drop
    :param user: The user who owns the model, if relevant.
    :return:
    """
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
    """
    Get the MongoDB connection associated with this app.

    :return: A MongoDB database.
    """
    if 'ga_dynamic_models' in settings.MONGODB_ROUTES:
        _db = settings.MONGODB_ROUTES['ga_dynamic_models']
    else:
        _db = settings.MONGODB_ROUTES['default']
    return _db

def get_model(model):
    """
    Get a Model class that's stored in this app.

    :param model:  The name of the model to return.
    :return: The model class as a Python class.
    """
    try:
        del sys.modules['ga_dynamic_models.models']
    except KeyError:
        pass

    models = importlib.import_module('ga_dynamic_models.models')
    if hasattr(models, model):
        return models.__getattribute__(model)
    else:
        raise AttributeError("No such model")


