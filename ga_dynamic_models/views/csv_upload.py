from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction

from ga_dynamic_models import utils
import csv
import re
from django.views.generic import FormView, TemplateView
from django import forms
from logging import getLogger
from ga_ows.utils import parsetime
from django.core.validators import RegexValidator
import cStringIO as StringIO

_log = getLogger(__name__)

def munge_col_to_name(name):
    name = re.sub('%', 'pct', name)
    name = re.sub('[^A-z0-9_]', '_', name).lower()
    if name[0] in '0123456789_':
        name = 'x' + name
    name = re.sub('__*', "_", name)
    name = re.sub('__*$', '', name)
    return name

def casify(name):
    name = name[0].lower() + name[1:]
    name = re.sub(r'([A-Z])', r'_\1', name).lower()
    return name

def model_from_csv(model_short_name, model_verbose_name, flo):
    csv_reader = csv.reader(StringIO.StringIO(re.sub("\r", "\n", flo.read())))
    column_verbose_names = [name.strip() for name in csv_reader.next()]
    column_short_names = [munge_col_to_name(name) for name in column_verbose_names]
    datatypes = [t.strip() for t in csv_reader.next()]

    fields = {}
    for x in range(len(column_verbose_names)):
        db_index = datatypes[x][0] == '*'
        if datatypes[x][0] == '*':
            datatypes[x] = datatypes[x][1:]

        if datatypes[x] == 'CharField':
            fields[ column_short_names[x] ] = utils.simple_field('CharField', verbose_name=column_verbose_names[x], help_text=column_verbose_names[x], max_length=255, null=True, db_index=db_index)
        else:
            fields[ column_short_names[x] ] = utils.simple_field(datatypes[x], verbose_name=column_verbose_names[x], help_text=column_verbose_names[x], null=True, db_index=db_index)

    model = utils.model(
        model_short_name,
        [utils.attribute('django.db.models', 'Model')],
        fields,
        verbose_name=model_verbose_name,
        managed=True
    )

    return zip(column_short_names, datatypes), model, csv_reader

def maybe(fun):
    global _log
    def wrapper(value, err):
        try:
            if value is not None:
                return fun(value)
            else:
                return None
        except ValueError:
            _log.warn(err)
    return wrapper

@maybe
def maybeint(value):
    return int(value)

@maybe
def maybebool(value):
    return bool(value)

@maybe
def maybefloat(value):
    return float(value)

@maybe
def maybedate(value):
    return parsetime(value)

def instances_from_rows(model, spec, reader):
    for row in reader:
        kwargs = {}
        for i, value in enumerate(row):
            field_name, data_type = spec[i]

            if data_type == 'CharField':
                    kwargs[field_name] = value
            elif data_type == 'IntegerField':
                kwargs[field_name] = maybeint(value, 'error converting {field_name} to int ({value})'.format(field_name=field_name,value=value))
            elif data_type == 'FloatField':
                kwargs[field_name] = maybefloat(value, "error converting {field_name} to float ({value})".format(field_name=field_name, value=value))
            elif data_type == 'DateField':
                kwargs[field_name] = maybedate(value, "error converting {field_name} to date ({value})".format(field_name=field_name, value=value))
            elif data_type == 'BooleanField':
                kwargs[field_name] = maybebool(value, "error converting {field_name} to boolean ({value})".format(field_name=field_name, value=value))

        yield model(**kwargs)

class CSVUploadForm(forms.Form):
    model_name = forms.CharField(max_length=255, validators=[RegexValidator('[A-z][A-z0-9]*')], label='Name of table (no spaces)')
    model_verbose_name = forms.CharField(max_length=255)
    model_data = forms.FileField()
    overwrite_existing = forms.MultipleChoiceField(choices=(('overwrite','overwrite'),('append','append'),('fail if already exists', 'fail')))

class CSVCreateModelView(FormView):
    form_class = CSVUploadForm
    template_name = 'ga_dynamic_models/csv_upload_view.template.html'
    success_url = '../csv_success'

    #@user_passes_test(lambda u: u.has_perm('ga_dynamic_models.can_upload_data'))

    def form_valid(self, form):
        print "form valid called. creating model from CSV file."
        spec, model, rows = model_from_csv(
            form.cleaned_data['model_name'],
            form.cleaned_data['model_verbose_name'],
            form.cleaned_data['model_data']
        )
        utils.drop_model(form.cleaned_data['model_name'])
        utils.drop_resource(form.cleaned_data['model_name'])
        utils.declare_model(model, syncdb=True)
        utils.declare_resource(utils.simple_model_resource(
            'ga_dynamic_models.models',
            form.cleaned_data['model_name'],
            casify(form.cleaned_data['model_name'])
        ))
        self.load_data(model['name'], spec, rows)
        return super(CSVCreateModelView, self).form_valid(form)

    @transaction.commit_on_success
    def load_data(self, model, spec, rows):
        m = utils.get_model(model)
        m.objects.all().delete()
        for instance in instances_from_rows(m, spec, rows):
            instance.save()

class CSVSuccessView(TemplateView):
    template_name = 'ga_dynamic_models/csv_load_data_success.template.html'