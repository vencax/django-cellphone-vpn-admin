import datetime
import os
import logging
from django.views.generic.edit import FormView
from django import forms
from django.utils.translation import ugettext, ugettext_lazy as _
from django.forms.widgets import Textarea
from django.conf import settings
from invoices.models import CompanyInfo
from django.contrib.sites.models import Site
from creditservices.signals import processCredit
from valueladder.models import Thing
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.views.generic.base import TemplateView

from .wholebillparser import WholeBillParser
from .models import PhoneServiceInfo
import StringIO
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.template.loader import render_to_string

FREE_MINS_COUNT = getattr(settings, 'FREE_MINS_COUNT', 5000)
FREE_SMS_COUNT = getattr(settings, 'FREE_SMS_COUNT', 1000)
SMS_PRICE = getattr(settings, 'SMS_PRICE', 1)
MINUTE_PRICE = getattr(settings, 'MINUTE_PRICE', 1.5)
INTERNET_PRICE = getattr(settings, 'INTERNET_PRICE', 66)

class BillUploadForm(forms.Form):
    bill = forms.FileField()
    billdata = forms.CharField(widget=Textarea)
    
def getBillFileName():
    return datetime.date.today().strftime('%Y-%m.pdf')

def getBillFilePath():
    return os.path.join(settings.MEDIA_ROOT, getBillFileName())

def getBillUrl():
    return '%s%s' % (settings.MEDIA_URL, getBillFileName())

SESSION_KEY = 'parsedInfo'

class UploadBillView(FormView):
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
        with open(getBillFilePath(), 'w') as f:
            f.write(form.cleaned_data['bill'].read())

        self.request.session[SESSION_KEY] = parsed
        
        return HttpResponseRedirect(reverse('processForm'))

class ProcessBillView(TemplateView):
    template_name = 'vpnadmin/dataProcessed.html'
    
    @method_decorator(login_required)
    @method_decorator(user_passes_test(lambda u: u.is_superuser))
    def dispatch(self, request, *args, **kwargs):
        return TemplateView.dispatch(self, request, *args, **kwargs)
    
    def get(self, request, *args, **kwargs):
        parsed = request.session.get(SESSION_KEY)
        newParsed = {}
        total = {
            'inVPN' : datetime.timedelta(),
            'outVPN' : datetime.timedelta(),
            'sms' : 0,
            'extra' : 0
        }
        for num, pinfo in parsed.items():
            try:
                cInfo = CompanyInfo.objects.get(phone=num)
                phoneInfo = PhoneServiceInfo.objects.get(user=cInfo.user)
            except PhoneServiceInfo.DoesNotExist:
                pass
            except CompanyInfo.DoesNotExist:
                pass
            
            inVPN = self._convertToTimeDelta(pinfo[0])
            outVPN = self._convertToTimeDelta(pinfo[1])
            aboveFreeMins = self._convertToMinutes(outVPN) - phoneInfo.minutes
            newParsed[num] = (inVPN, outVPN, pinfo[2], cInfo, 
                              aboveFreeMins, phoneInfo, pinfo[3])
            if phoneInfo.internet:
                del(pinfo[3]['data'])
            total['inVPN'] += inVPN
            total['outVPN'] += outVPN
            total['sms'] += pinfo[2]
            total['extra'] += sum(pinfo[3].values())
        total['inVPNMins'] = self._convertToMinutes(total['inVPN'])
        total['outVPNMins'] = self._convertToMinutes(total['outVPN'])
        
        expectedInvoicePrice = total['extra'] + 5526
        if total['outVPNMins'] > FREE_MINS_COUNT:
            expectedInvoicePrice += ((total['outVPNMins'] - FREE_MINS_COUNT) * MINUTE_PRICE)
        if total['sms'] > FREE_SMS_COUNT:
            expectedInvoicePrice += ((total['sms'] - FREE_SMS_COUNT) * SMS_PRICE)
            
        return self.render_to_response({
            'billurl' : getBillUrl(), 
            'parsed' : newParsed,
            'totals' : total,
            'expectedInvoicePrice' : expectedInvoicePrice
        })
    
    def post(self, request, *args, **kwargs):
        parsed = request.session.get(SESSION_KEY)
        invoices = self._processParsedData(parsed)
        billurl = getBillUrl()
        self.processInvoices(invoices, billurl)
        
        message = _('''%(count)i records processed OK.
Bill is <a href="%(billurl)s">here</a>''') % {'count': len(invoices),
                                              'billurl' :billurl}
        
        return self.render_to_response({'message' : message})
        
    def processInvoices(self, invoices, billURL):
        for invoice, cinfo in invoices:
            if cinfo.user_id == settings.OUR_COMPANY_ID:
                continue
            price = sum(invoice.values())
            currency = Thing.objects.get_default()
            contractor = CompanyInfo.objects.get_our_company_info()
            details = '\n'.join(['%s:%s' % (k, v) for k, v in invoice.items()])
            state = processCredit(cinfo, -price, currency, details, 
                                  contractor.bankaccount)
            
            mailContent = render_to_string('vpnadmin/infoMail.html', {
                'invoice' : invoice,
                'state' : state.value,
                'billURL' : billURL,
                'price' : price,
                'domain' : Site.objects.get_current(),
            })
            cinfo.user.email_user(ugettext('phone service info'), 
                                         mailContent)

    def _processParsedData(self, parsed):
        invoices = []
        smsPerPerson = FREE_SMS_COUNT / PhoneServiceInfo.objects.all().count()
        for telnum, info in parsed.items():
            invoices.append(self._processParsedRec(telnum, info, smsPerPerson))
        return invoices

    def _processParsedRec(self, telnum, info, smsPerPerson):
        try:
            cinfo = CompanyInfo.objects.get(phone=telnum)            
            psi = PhoneServiceInfo.objects.get(user=cinfo.user)
            
            inside, ouside, sms, extra = info
            
            outsideVPN = self._convertToMinutes(
                self._convertToTimeDelta(ouside))
            insideVPN = self._convertToMinutes(
                self._convertToTimeDelta(inside))
            minsOver = outsideVPN - psi.minutes
            smsOver = sms - smsPerPerson
             
            invoice = {_('freeMins') + '(%i min)' % psi.minutes: psi.minutes,
                       _('inVPN') + '(%i min)' % insideVPN : 0}            
            if minsOver > 0:
                p = minsOver * MINUTE_PRICE
                invoice[_('extraMinutes') + '(%i min)' % minsOver] = p
            if smsOver > 0:
                p = smsOver * SMS_PRICE
                invoice[_('extraSMS') + '(%i ks)' % smsOver] = p
            
            invoice.update(extra)
            
            if psi.internet:
                invoice['data'] = INTERNET_PRICE
                
            return (invoice, cinfo)
        except Exception, e:
            logging.exception(e)
            
    def _convertToTimeDelta(self, time):
        parts = time.split(':')
        return datetime.timedelta(hours=int(parts[0]), 
                                  minutes=int(parts[1]), 
                                  seconds=int(parts[2]))
        
    def _convertToMinutes(self, time):
        return (time.days * 24 * 60) + (time.seconds / 60)