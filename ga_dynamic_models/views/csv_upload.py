
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django import forms
from django import shortcuts
from django.template.context import RequestContext
from ga_dynamic_models import tasks

from ga_dynamic_models import utils
import csv
import re
from django.views.generic import TemplateView, FormView
from django.views.generic.edit import BaseFormView
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

    def render_to_response(self, context, **response_kwargs):
        tasks.restart_ga.delay()
        return super(CSVSuccessView.render_to_response(context, **response_kwargs))

class CSVUploadView2(TemplateView):
    template_name = 'ga_dynamic_models/csv_upload_view2.template.html'
    validates_columns = False
    columns_validated = None

    def get_context_data(self, **kwargs):
            ctx = {}
            ctx['existing_models'] = zip(utils.get_models(), utils.get_models())
            ctx['validates_columns'] = self.validates_columns
            ctx['columns_validated'] = self.columns_validated
            return RequestContext(self.request, dict=ctx)

class CSVUploadAcceptForm(forms.Form):
    file = forms.FileField()


class CSVUploadAccept(FormView):
    file_must_contain_columns = set()
    column_valid_values = {}
    column_invalid_values = {}
    template_name = ''

    form_class = CSVUploadAcceptForm

    def form_valid(self, form):
        try:
            data = re.sub("\r", "\n", form.cleaned_data['file'].read())
            csv_reader = csv.reader(StringIO.StringIO(data))
            column_verbose_names = [name.strip() for name in csv_reader.next()]
            column_short_names = [munge_col_to_name(name) for name in column_verbose_names]
            datatypes = [t.strip() for t in csv_reader.next()]

            self.request.session['uploaded_csv_data'] = data
            self.request.session['datatypes'] = datatypes
            self.request.session['column_short_names'] = column_short_names
            self.request.session['column_verbose_names'] = column_verbose_names


            col_indices = dict(zip(column_short_names, range(len(column_short_names))))
            if self.file_must_contain_columns:
                if self.file_must_contain_columns.intersection(column_short_names) != self.file_must_contain_columns:
                    raise ValueError("File must contain columns: {cols}".format(cols=', '.join(self.file_must_contain_columns)))

            rowcount = 1
            errors = []
            rows = [csv_reader.next()]
            for row in csv_reader:
                if rowcount <= 5:
                    rows.append(row)
                rowcount += 1
                if self.column_valid_values:
                    for col in self.column_valid_values:
                        ix = col_indices[col]
                        if row[ix] not in self.column_valid_values[col]:
                            errors.append("Error on row {row}, column {col}: '{val}' is not in the list of valid values. Check its spelling and capitalization.".format(
                                row = rowcount,
                                col = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"[ix],
                                val = row[ix]
                            ))

                if self.column_invalid_values:
                    for col in self.column_invalid_values:
                        ix = col_indices[col]
                        if row[ix]  in self.column_invalid_values[col]:
                            errors.append("Error on row {row}, column {col}: '{val}' is an invalid value. Check its spelling and capitalization.".format(
                                row = rowcount,
                                col = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"[ix],
                                val = row[ix]
                            ))

            if errors:
                return shortcuts.render_to_response('ga_dynamic_models/upload_error.template.html', { 'errors' : errors })

            indexed = []
            for col_num, datatype in enumerate(datatypes):
                if not datatype:
                    raise ValueError("data in column '{colname}' has no data type associated with it".format(colname=column_verbose_names[col_num]))
                else:
                    if datatype[0] == '*':
                        datatype = datatype[1:]
                        indexed.append('indexed_column')
                    else:
                        indexed.append('column')

                if datatype not in ['CharField','IntegerField','FloatField','BooleanField']:
                    raise ValueError("datatype for column '{colname}' was '{dtype}', but must be in the set [CharField, IntegerField, FloatField, or BooleanField]".format(
                        colname = column_verbose_names[col_num],
                        dtype = datatype
                    ))

            return shortcuts.render_to_response('ga_dynamic_models/upload_spotcheck.template.html', {
                'column_names' : zip(column_verbose_names, indexed),
                'datatypes' : zip(datatypes, indexed),
                'rows' : [zip(row, indexed) for row in rows],
                'rowcount' : rowcount
            })
        except Exception as ex:
            return shortcuts.render_to_response('ga_dynamic_models/upload_error.template.html', { 'errors' : [str(ex)] })

    def form_invalid(self, form):
        return shortcuts.render_to_response('ga_dynamic_models/upload_error.template.html', {'errors' : ["No file or empty file uploaded"] })


