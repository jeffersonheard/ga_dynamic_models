RENCI Geoanalytics - Dynamic model infrastructure
#################################################

To facilitate a "push-to-publish" model of data publishing, RENCI's Geoanalytics introduces "dynamic models" to Django.
Dynamic models allow you to build forms and views that will allow a user to upload data in a controlled fashion.  This
data will then populate a database table or series of tables in the ORM.  Models will be generated and these models will
be automagically exposed to the Admin interface and can be added dynamically to RESTful APIs as well through Tastypie.

In the near future, you will also be able to expose these models via WFS and WMS using Geoanalytics OWS services.

Requirements beyond basic Django
================================

ga_dynamic_models requires a version of pymongo on your system and a writable MongoDB instance, as dynamic models are
stored in MongoDB as documents.

Once you have this, add lines to your ``settings.py`` file like this::

    MONGODB_CONNECTIONS = {
        'default' : pymongo.Connection()
    }

    MONGODB_ROUTES = {
        'default' : MONGODB_CONNECTIONS['default']['default_collection']  # CONNECTIONS['connection']['database']
        'ga_dynamic_models : MONGODB_CONNECTIONS['default']['ga_dynamic_models']
    }

These are used by other apps as well, and effectively create a routing mechanism for connections that use the raw
``pymongo`` driver.  The values in MONGODB_ROUTES can change depending on your particular database configuration.  If
``ga_dynamic_models`` is listed as a route in the settings, then this app will use that route, otherwise it will use
 the default route and create two new collections, ``ga_dynamic_models__models`` and ``ga_dynamic_models__apis``.


Getting started
===============

This app is still very early in its development stage.  Although it is working,
parts of the application regarding management are currently lacking. Currently
there are no management views setup for this application.  Furthermore there
are no default forms setup for creating dynamic models.  There will be soon,
but for now this application seems useful and generic enough to make available.

Once you have fulfilled the main requirements, add ``ga_dynamic_models`` to your INSTALLED_APPS section in Django's
settings, and add an entry for ga_dynamic_models.urls in your main ``urls.py``.  This will create an endpoint at
``^/api/ga_dynamic_models`` that will build out as more dynamic models are added.  See the `django tastypie`_
documentation for more details on how Tastypie RESTful APIs work.  They are largely compatible with popular client-side
libraries like `jQuery`_, `jQueryMobile`_, `ExtJS4`_, and `Sencha Touch`_.

.. _jQuery: http://jquery.org
.. _jQueryMobile: http://jquerymobile.com
.. _ExtJS4: http://sencha.com
.. _Sencha Touch: http://sencha.com/touch
.. _django tastypie: http://http://django-tastypie.readthedocs.org/

Creating a model
----------------

The only way to create a model right now is in Python code.  The module ``ga_dynamic_models.utils`` contains tools to
help you do this.  The simplest way is to use the ``declare_model`` function and the ``simple_(geo)model`` function
like so::

    from ga_dynamic_models.utils import *

Then declare a new geographic model::

    declare_model(simple_geomodel('MyGeoModel',
        geom = simple_geofield('PointField'),
        some_name = simple_geofield('CharField', max_length=255, default='', null=True, db_index=True),
        some_integer = simple_geofield("IntegerField", default=10)
    ))

Or declare a new regular model::

    declare_model(simple_model("MyRegularModel",
        some_name = simple_field('CharField', max_length=255, default='', null=True, db_index=True),
        some_integer = simple_field("IntegerField", default=10)
    ))

Then if you want to expose these as RESTful services via Tastypie, you can do this::

    declare_resource(simple_model_resource(
        'ga_dynamic_models.models',
        'MyRegularModel',
        "my_regular_model"
    ))

    declare_resource(simple_geo_resource(
        'ga_dynamic_models.models',
        'MyGeoModel',
        'my_geo_model'
    ))

The ``declare_model`` function adds a new model to the list.  Note this does NOT create any tables in your main database.
To do that, you MUST run the ``syncdb`` task yourself, or achieve this in code.  It does however, expose the model to
the Admin interface, if you have enabled the admin application.

The ``declare_resource`` function adds a model to the API.  See the utils module for more details on how these functions
work and the `Django model Meta options`_ and `Tastypie Meta options`_ pages on what extra meta options can be passed
to these functions.  More documentation will be forthcoming on this module, but for now you're kind of going to be
stuck reading the code a bit.  Check the ``tests.py`` file for examples of usage.

.. _Django model Meta options: https://docs.djangoproject.com/en/dev/ref/models/options/
.. _Tastypie Meta options: http://django-tastypie.readthedocs.org/en/latest/resources.html#resource-options-aka-meta


Support
=======

Please post issues at `github's`_ repository for `ga_dynamic_models` for support.

.. _github's: http://www.github.com/JeffHeard
