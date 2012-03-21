import django.contrib.gis.admin as geoadmin
import django.contrib.admin as admin
from django.contrib.gis.db.models import GeoManager
import ga_dynamic_models.models as m
import importlib
from django.db.models import Model
from datetime import datetime
from ga_dynamic_models import utils

__now__ = datetime.utcnow()

from django.core.signals import request_started

def my_callback(sender, *args, **kwargs):
    utils.reload_if_updated(__now__, __name__)

request_started.connect(my_callback)


for model in [m.__getattribute__(x) for x in m.__all__]:
    try:
        if issubclass(model, Model):
            if hasattr(model._meta, "admin_class"):
                module = importlib.import_module(model._meta.admin_class['module'])
                cls = module.__getattribute__(model._meta.admin_class["attribute"])
                admin.site.register(model, cls)
            elif isinstance(model.objects, GeoManager):
                admin.site.register(model, geoadmin.OSMGeoAdmin)
            else:
                admin.site.register(model, admin.ModelAdmin)
    except TypeError:
        pass

