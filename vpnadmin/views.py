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
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from creditservices.models import CreditChangeRecord

FREE_MINS_COUNT = getattr(settings, 'FREE_MINS_COUNT', 5000)
FREE_SMS_COUNT = getattr(settings, 'FREE_SMS_COUNT', 1000)
SMS_PRICE = getattr(settings, 'SMS_PRICE', 1)
MINUTE_PRICE = getattr(settings, 'MINUTE_PRICE', 1.5)
INTERNET_PRICE = getattr(settings, 'INTERNET_PRICE', 66)
FREE_SMS_RATIO = float(FREE_SMS_COUNT) / FREE_MINS_COUNT

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
DATA_SK = 'dataInfo'

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
        data = {}
        total = {
            'inVPN' : datetime.timedelta(),
            'outVPN' : datetime.timedelta(),
            'sms' : 0,
            'extra' : 0
        }
        for num, pinfo in parsed.items():
            timeInVPN, timeOutsideVPN, smsCount, extra, vpnSmsCount = pinfo
            try:
                cInfo = CompanyInfo.objects.get(phone=num)
                phoneInfo = PhoneServiceInfo.objects.get(user=cInfo.user)
            except PhoneServiceInfo.DoesNotExist:
                pass
            except CompanyInfo.DoesNotExist:
                pass

            inVPN = self._convertToTimeDelta(timeInVPN)
            outVPN = self._convertToTimeDelta(timeOutsideVPN)
            aboveFreeMins = self._convertToMinutes(outVPN) - phoneInfo.minutes
                
            nonVPNSMS = smsCount - vpnSmsCount
            smsOver = nonVPNSMS - (phoneInfo.minutes * FREE_SMS_RATIO)
            if smsOver < 0:
                smsOver = 0
            
            if phoneInfo.internet:
                del(extra['data'])
            
            total['inVPN'] += inVPN
            total['outVPN'] += outVPN
            total['sms'] += nonVPNSMS
            total['extra'] += sum(extra.values())
            
            if phoneInfo.internet:
                pinfo[3]['data'] = INTERNET_PRICE 
            
            data[num] = (inVPN, outVPN, smsCount, cInfo, aboveFreeMins, 
                         phoneInfo, extra, vpnSmsCount, smsOver)
            
        total['inVPNMins'] = self._convertToMinutes(total['inVPN'])
        total['outVPNMins'] = self._convertToMinutes(total['outVPN'])

        expectedInvoicePrice = total['extra'] + 5526
        if total['outVPNMins'] > FREE_MINS_COUNT:
            expectedInvoicePrice += ((total['outVPNMins'] - FREE_MINS_COUNT) * MINUTE_PRICE)
        if total['sms'] > FREE_SMS_COUNT:
            expectedInvoicePrice += ((total['sms'] - FREE_SMS_COUNT) * SMS_PRICE)
            
        request.session[DATA_SK] = data

        return self.render_to_response({
            'billurl' : getBillUrl(),
            'parsed' : data,
            'totals' : total,
            'expectedInvoicePrice' : expectedInvoicePrice
        })

    def post(self, request, *args, **kwargs):
        data = request.session.get(DATA_SK)
        invoices = self._processParsedData(data)
        billurl = getBillUrl()
        self.processInvoices(invoices, billurl)

        message = _('''%(count)i records processed OK.
Bill is <a href="%(billurl)s">here</a>''') % {'count': len(invoices),
                                              'billurl' :billurl}
        del(request.session[DATA_SK])
        del(request.session[SESSION_KEY])
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
                'cinfo': cinfo,
                'domain' : Site.objects.get_current(),
            })
            cinfo.user.email_user(ugettext('phone service info'),
                                         mailContent)

    def _processParsedData(self, parsed):
        invoices = []
        for telnum, info in parsed.items():
            invoices.append(self._processParsedRec(telnum, info))
        return invoices

    def _processParsedRec(self, telnum, info):
        try:
            cinfo = CompanyInfo.objects.get(phone=telnum)
            psi = PhoneServiceInfo.objects.get(user=cinfo.user)
            
            (inVPN, outVPN, smsCount, cInfo, aboveFreeMins, #@UnusedVariable
             phoneInfo, extra, vpnSmsCount, smsOver) = info #@UnusedVariable

            outsideVPN = self._convertToMinutes(outVPN)
            insideVPN = self._convertToMinutes(inVPN)
            minsOver = outsideVPN - psi.minutes

            invoice = {_('freeMins') + '(%i min)' % psi.minutes: psi.minutes,
                       _('inVPN') + '(%i min)' % insideVPN : 0,
                       _('free SMS') + '(%i ks)' % (psi.minutes * FREE_SMS_RATIO): 0,
                       _('sms in vpn') + '(%i ks)' % vpnSmsCount: 0}
            if minsOver > 0:
                p = minsOver * MINUTE_PRICE
                invoice[_('extraMinutes') + '(%i min)' % minsOver] = p
            if smsOver > 0:
                p = smsOver * SMS_PRICE
                invoice[_('extraSMS') + '(%i ks)' % smsOver] = p

            invoice.update(extra)

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
    
class InfoView(TemplateView):
    template_name = 'vpnadmin/info.html'
    
    def get_context_data(self, **kwargs):
        chageRecords = CreditChangeRecord.objects.filter(user=self.user)
        return {'credRecords': chageRecords, 'vpnuser': self.user}
        
    def get(self, request, *args, **kwargs):
        self.user = get_object_or_404(User, id=kwargs['uid'])
        return super(InfoView, self).get(request, *args, **kwargs)