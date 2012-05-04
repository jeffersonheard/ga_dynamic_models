from django.conf.urls.defaults import patterns, url, include
from ga_dynamic_models.api import api
from ga_dynamic_models.views import csv_upload
from ga_dynamic_models.views import iei_commons

#
# This file maps views to actual URL endpoints.
#

urlpatterns = patterns('',
    url(r'^api/', include(api.urls)),
    url(r'^csv_create_model/', csv_upload.CSVCreateModelView.as_view()),
    url(r'^csv_success/', csv_upload.CSVSuccessView.as_view()),
    url(r'^$', iei_commons.CountyRestrictedUploadPage.as_view()),
    url(r'^upload/', iei_commons.CountyRestrictedCSVUpload.as_view()),
    url(r'^schema_editor/', iei_commons.CSVSchemaEditor.as_view())
)
