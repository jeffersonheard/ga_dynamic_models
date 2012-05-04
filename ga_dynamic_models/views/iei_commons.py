from django.template.context import RequestContext
from ga_dynamic_models.views import csv_upload
from django import forms, shortcuts
from django.views.generic import FormView, TemplateView
from django.forms.formsets import formset_factory

class ModelMetadataForm(forms.Form):
    title = forms.CharField()
    description = forms.CharField()
    category = forms.CharField()
    subcategory = forms.CharField()


class SchemaElementForm(forms.Form):
    name = forms.HiddenInput()
    datatype = forms.HiddenInput()
    title = forms.CharField()
    description = forms.CharField(min_length=0)
    type = forms.ChoiceField(choices=(('categorical','categorical'), ('numerical','numerical')))
    units = forms.CharField(min_length=0)
    null_okay = forms.BooleanField(initial=False)


SchemaFormset  = formset_factory(SchemaElementForm)

class CSVSchemaEditor(TemplateView):
    template_name = 'ga_dynamic_models/schema_editor.template.html'

    def get_context_data(self, **kwargs):
        datatypes = self.request.session['datatypes']
        column_short_names = self.request.session['column_short_names']
        column_verbose_names = self.request.session['column_verbose_names']

        initial_data = [{
            "name" : column_short_names[i],
            "datatype" : datatypes[i],
            "title" : column_verbose_names[i],
            "null_okay" : False,
            "unique" : False,
            "description" : column_verbose_names[i]
        } for i in range(len(datatypes))]

        return RequestContext(self.request, { 'formset' : SchemaFormset(initial=initial_data), 'model_metadata' : ModelMetadataForm() })


class CountyRestrictedUploadPage(csv_upload.CSVUploadView2):
    validates_columns = True
    columns_validated = [
        'county - column must exist and values must be completely lowercase NC county name'
    ]


class CountyRestrictedCSVUpload(csv_upload.CSVUploadAccept):
    file_must_contain_columns = {'county'}
    column_valid_values = {
        'county' : {
            "alamance","alexander","alleghany","anson","ashe","avery",
            "beaufort","bertie","bladen","brunswick","buncombe","burke",
            "cabarrus","caldwell","camden","carteret","caswell","catawba",
            "chatham","cherokee","chowan","clay","cleveland","columbus",
            "craven","cumberland","currituck","dare","davidson","davie",
            "duplin","durham","edgecombe","forsyth","franklin","gaston",
            "gates","graham","granville","greene","guilford","halifax",
            "harnett","haywood","henderson","hertford","hoke","hyde",
            "iredell","jackson","johnston","jones","lee","lenoir",
            "lincoln","macon","madison","martin","mcdowell","mecklenburg",
            "mitchell","montgomery","moore","nash","new hanover","northampton",
            "onslow","orange","pamlico","pasquotank","pender","perquimans",
            "person","pitt","polk","randolph","richmond","robeson",
            "rockingham","rowan","rutherford","sampson","scotland","stanly",
            "stokes","surry","swain","transylvania","tyrrell","union",
            "vance","wake","warren","washington","watauga","wayne",
            "wilkes","wilson","yadkin","yancey"
        }
    }
