from django.views.generic.edit import FormView
from django.db.transaction import commit_on_success
from django import forms
from django.utils.translation import ugettext, ugettext_lazy as _
from django.forms.widgets import Textarea
from django.core.exceptions import ValidationError
from django.conf import settings
from invoices.models import CompanyInfo, Invoice, Item
import datetime
import os
from django.contrib.sites.models import Site
from creditservices.signals import processCredit
import logging

from .billparser import parseBill

class BillUploadForm(forms.Form):
    bill = forms.FileField()
    resume = forms.CharField(widget=Textarea)
    total = forms.FloatField(_('total'),
                             help_text=_('fill the total amount on the invoice for check.'))

    def clean(self):
        data = forms.Form.clean(self)
        parsedData = parseBill(data['resume'])
        parsedTotal = 0
        for _, price in parsedData:
            parsedTotal += price
        if not self._isEqualTheGivenTotal(data['total'],
                                          (parsedTotal * settings.DPH)):
            raise ValidationError(ugettext(\
                    'Given total does not match the parsed data total'))
        data['parsedData'] = parsedData
        return data

    def _isEqualTheGivenTotal(self, total, givenTotal):
        if total >= (givenTotal - 0.1) and \
            total <= (givenTotal + 0.1):
            return True
        return False


class UploadBillView(FormView):
    template_name = 'vpnadmin/uploaddata.html'
    form_class = BillUploadForm

    def form_valid(self, form):
        parsed = form.cleaned_data['parsedData']
        invoices = self._processParsedData(parsed)
        # save the bill file
        filename = datetime.date.today().strftime('%Y-%m.pdf')
        filepath = os.path.join(settings.MEDIA_ROOT, filename)
        with open(filepath, 'w') as f:
            f.write(form.cleaned_data['bill'].read())

        billurl = '%s%s' % (settings.MEDIA_URL, filename)
        self.processInvoices(invoices, billurl)

        message = _('''data processed OK. %(count)i new invoices.
Bill is <a href="%(billurl)s">here</a>''') % {'count': len(invoices),
                                              'billurl' :billurl}
        return self.render_to_response({'message' : message})

    def processInvoices(self, invoices, billURL):
        extra = 'PS: %s: %s%s' % (ugettext('Bill file can be found here'),
                                  Site.objects.get_current(), billURL)
        for i, price in invoices:
            val = -price * settings.DPH
            processCredit(i.subscriber, val, i.currency,
                          i.contractor.bankaccount)
            i.send(extraContent = extra)

    @commit_on_success
    def _processParsedData(self, parsed):
        invoices = []
        for telnum, price in parsed:
            self._processParsedRec(telnum, price, invoices)
        return invoices

    def _processParsedRec(self, telnum, price, invoices):
        try:
            cinfo = CompanyInfo.objects.get(phone=telnum)
            if cinfo.user_id == settings.OUR_COMPANY_ID:
                return  # do not generate invoice to self
            invoice = Invoice(subscriber=cinfo, direction='o')
            invoice.save()
            invoice.items.add(Item(price=0, name=ugettext('Phone services') +\
                                    ' - ' + ugettext('reinvoicing')))
            invoices.append((invoice, price))
        except Exception, e:
            logging.exception(e)
