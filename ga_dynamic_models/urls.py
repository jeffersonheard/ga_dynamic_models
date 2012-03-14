from django.conf.urls.defaults import patterns, url, include
from ga_dynamic_models.api import api

#
# This file maps views to actual URL endpoints.
#

urlpatterns = patterns('',
    url(r'^api/', include(api.urls))
)
