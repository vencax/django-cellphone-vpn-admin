import datetime
import os
import logging
from django.views.generic.edit import FormView
from django.db.transaction import commit_on_success
from django import forms
from django.utils.translation import ugettext, ugettext_lazy as _
from django.forms.widgets import Textarea
from django.conf import settings
from invoices.models import CompanyInfo, Invoice, Item
from django.contrib.sites.models import Site
from creditservices.signals import processCredit
from django.http import HttpResponseRedirect
from django.core.urlresolvers import reverse
from django.views.generic.base import TemplateView

from .wholebillparser import WholeBillParser
from .models import PhoneServiceInfo
import StringIO
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.decorators import method_decorator
from django.template.loader import render_to_string

FREE_SMS_COUNT = getattr(settings, 'FREE_SMS_COUNT', 1000)
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
            'sms' : 0
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
            newParsed[num] = (inVPN, outVPN, pinfo[2], cInfo, aboveFreeMins, phoneInfo)
            total['inVPN'] += inVPN
            total['outVPN'] += outVPN
            total['sms'] += pinfo[2]
        total['inVPNMins'] = self._convertToMinutes(total['inVPN'])
        total['outVPNMins'] = self._convertToMinutes(total['outVPN'])
            
        return self.render_to_response({
            'billurl' : getBillUrl(), 
            'parsed' : newParsed,
            'totals' : total
        })
    
    def post(self, request, *args, **kwargs):
        parsed = request.session.get(SESSION_KEY)
        invoices = self._processParsedData(parsed)
        billurl = getBillUrl()
        self.processInvoices(invoices, billurl)
        
        message = _('''data processed OK. %(count)i new invoices.
Bill is <a href="%(billurl)s">here</a>''') % {'count': len(invoices),
                                              'billurl' :billurl}
        
        return self.render_to_response({'message' : message})
        
    def processInvoices(self, invoices, billURL):
        for i, price, info in invoices:
            inside, ouside, sms, minsOver = info
            state = processCredit(i.subscriber, -price, i.currency,
                                  i.contractor.bankaccount)
            i.send()
            
            mailContent = render_to_string('vpnadmin/infoMail.html', {
                'inside' : inside,
                'ouside' : ouside,
                'sms' : sms,
                'minsOver' : minsOver,
                'state' : state,
                'billURL' : billURL,
                'domain' : Site.objects.get_current(),
            })
            i.subscriber.user.email_user(ugettext('phone service info'), 
                                         mailContent)

    @commit_on_success
    def _processParsedData(self, parsed):
        invoices = []
        smsPerPerson = FREE_SMS_COUNT / PhoneServiceInfo.objects.all().count()
        for telnum, info in parsed.items():
            self._processParsedRec(telnum, info, smsPerPerson, invoices)
        return invoices

    def _processParsedRec(self, telnum, info, smsPerPerson, invoices):
        try:
            cinfo = CompanyInfo.objects.get(phone=telnum)
            if cinfo.user_id == settings.OUR_COMPANY_ID:
                return  # do not generate invoice to self
            
            psi = PhoneServiceInfo.objects.get(user=cinfo.user)
            
            inside, ouside, sms = info
            outsideVPN = self._convertToMinutes(
                self._convertToTimeDelta(ouside))
            minsOver = outsideVPN - psi.minutes
            smsOver = sms - smsPerPerson
             
            invoice = Invoice(subscriber=cinfo, direction='o')
            invoice.save()
            
            price = psi.minutes
            if minsOver > 0:
                price += minsOver * MINUTE_PRICE
            if smsOver > 0:
                price += smsOver
            if psi.internet:
                price += INTERNET_PRICE
                
            invoice.items.add(Item(price=0, name=ugettext('Phone services') +\
                                    ' - ' + ugettext('reinvoicing')))
            invoices.append((invoice, price, (inside, ouside, sms, minsOver)))
            
        except Exception, e:
            logging.exception(e)
            
    def _convertToTimeDelta(self, time):
        parts = time.split(':')
        return datetime.timedelta(hours=int(parts[0]), 
                                  minutes=int(parts[1]), 
                                  seconds=int(parts[2]))
        
    def _convertToMinutes(self, time):
        return (time.days * 24 * 60) + (time.seconds / 60)