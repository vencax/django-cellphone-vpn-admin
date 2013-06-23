
import os
import datetime
import StringIO

from django.views.generic.edit import FormView
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.forms.widgets import Textarea
from django.conf import settings
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.views.generic.base import TemplateView
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator

from .bill_processing import data_processing
from .bill_processing.wholebillparser import WholeBillParser


class BillUploadForm(forms.Form):
    bill = forms.FileField()
    day = forms.DateField(initial=datetime.date.today())
    billdata = forms.CharField(widget=Textarea)


def getBillFileName(day):
    return day.strftime('%Y-%m.pdf')


def getBillFilePath(day):
    return os.path.join(settings.MEDIA_ROOT, getBillFileName(day))


def getBillUrl(day):
    return '%s%s' % (settings.MEDIA_URL, getBillFileName(day))

SESSION_KEY = 'parsedInfo'
DATA_SK = 'dataInfo'
DAY_SK = 'day'


class UploadBillView(FormView):
    """
    Form for input actual operator invoice content and invoice PDF.
    """
    template_name = 'vpnadmin/uploaddata.html'
    form_class = BillUploadForm

    @method_decorator(login_required)
    @method_decorator(user_passes_test(lambda u: u.is_superuser))
    def dispatch(self, request, *args, **kwargs):
        return FormView.dispatch(self, request, *args, **kwargs)

    def form_valid(self, form):
        parser = WholeBillParser()
        stringStream = StringIO.StringIO(form.cleaned_data['billdata'])
        parsed = parser.parse(stringStream)
        # save the bill file

        day = form.cleaned_data['day']
        self.request.session[DAY_SK] = day

        with open(getBillFilePath(day), 'w') as f:
            f.write(form.cleaned_data['bill'].read())

        self.request.session[SESSION_KEY] = parsed

        return HttpResponseRedirect(reverse('processForm'))


class ProcessBillView(TemplateView):
    """
    Shows parsed operator invoice content in table along with
    expected invoice price.
    """
    template_name = 'vpnadmin/dataProcessed.html'

    @method_decorator(login_required)
    @method_decorator(user_passes_test(lambda u: u.is_superuser))
    def dispatch(self, request, *args, **kwargs):
        return TemplateView.dispatch(self, request, *args, **kwargs)

    def get(self, request, *args, **kwargs):
        parsed = request.session.get(SESSION_KEY)
        try:
            data, expectedInvoicePrice, total = \
                data_processing.get_service_stats(parsed)
        except data_processing.DataProcessingError, e:
            return self.render_to_response({
                'expectedInvoicePrice': str(e)
            })

        request.session[DATA_SK] = data

        return self.render_to_response({
            'billurl': getBillUrl(request.session[DAY_SK]),
            'parsed': data,
            'totals': total,
            'expectedInvoicePrice': expectedInvoicePrice
        })

    def post(self, request, *args, **kwargs):
        data = request.session.get(DATA_SK)
        invoices = data_processing.processParsedData(data)
        billurl = getBillUrl(request.session[DAY_SK])
        data_processing.processInvoices(invoices, billurl)

        message = _('''%(count)i records processed OK.
Bill is <a href="%(billurl)s">here</a>''') % {'count': len(invoices),
                                              'billurl': billurl}
        del(request.session[DATA_SK])
        del(request.session[SESSION_KEY])
        return self.render_to_response({'message': message})
