'''
Created on Jun 22, 2013

@author: vencax
'''
import logging
import datetime
from django.conf import settings
from django.template.loader import render_to_string
from django.contrib.sites.models import Site
from django.utils.translation import ugettext, ugettext_lazy as _
from creditservices.models import CompanyInfo
from creditservices.signals import processCredit
from vpnadmin.models import PhoneServiceInfo
from valueladder.models import Thing


FREE_MINS_COUNT = getattr(settings, 'FREE_MINS_COUNT', 5000)
FREE_SMS_COUNT = getattr(settings, 'FREE_SMS_COUNT', 1000)
SMS_PRICE = getattr(settings, 'SMS_PRICE', 1)
MINUTE_PRICE = getattr(settings, 'MINUTE_PRICE', 1.5)
INTERNET_PRICE = getattr(settings, 'INTERNET_PRICE', 66)
PROCESSING_FEE = getattr(settings, 'PROCESSING_FEE', 0)


class DataProcessingError(Exception):
    pass


def get_service_stats(parsed):
    """
    Creates set of info how much a person calls ...
    """
    data = {}
    total = {
        'inVPN': datetime.timedelta(),
        'outVPN': datetime.timedelta(),
        'sms': 0,
        'extra': 0
    }
    for num, pinfo in parsed.items():
        timeInVPN, timeOutsideVPN, smsCount, extra, vpnSmsCount = pinfo
        try:
            cInfo = CompanyInfo.objects.get(phone=num)
            phoneInfo = PhoneServiceInfo.objects.get(user=cInfo.user)
        except PhoneServiceInfo.DoesNotExist:
            m = 'Phone service info for %s not exists' % cInfo.user
            raise DataProcessingError(m)
        except CompanyInfo.DoesNotExist:
            raise DataProcessingError('Company (phone %s) not exists' % num)

        inVPN = _convertToTimeDelta(timeInVPN)
        outVPN = _convertToTimeDelta(timeOutsideVPN)
        aboveFreeMins = _convertToMinutes(outVPN) - phoneInfo.minutes

        nonVPNSMS = smsCount - vpnSmsCount
        smsOver = nonVPNSMS - phoneInfo.smsCount
        if smsOver < 0:
            smsOver = 0

        if phoneInfo.internet and 'data' in extra:
            del(extra['data'])

        total['inVPN'] += inVPN
        total['outVPN'] += outVPN
        total['sms'] += nonVPNSMS
        total['extra'] += sum(extra.values())

        if phoneInfo.internet:
            pinfo[3]['data'] = INTERNET_PRICE

        data[num] = (inVPN, outVPN, smsCount, cInfo, aboveFreeMins,
                     phoneInfo, extra, vpnSmsCount, smsOver)

    total['inVPNMins'] = _convertToMinutes(total['inVPN'])
    total['outVPNMins'] = _convertToMinutes(total['outVPN'])

    expectedInvoicePrice = total['extra'] + 5526
    if total['outVPNMins'] > FREE_MINS_COUNT:
        expectedInvoicePrice += \
            ((total['outVPNMins'] - FREE_MINS_COUNT) * MINUTE_PRICE)
    if total['sms'] > FREE_SMS_COUNT:
        expectedInvoicePrice += \
            ((total['sms'] - FREE_SMS_COUNT) * SMS_PRICE)

    return data, expectedInvoicePrice, total


def processInvoices(invoices, billURL):
    for invoice, cinfo in invoices:
        if cinfo.user_id == settings.OUR_COMPANY_ID:
            continue
        price = sum(invoice.values())
        currency = Thing.objects.get_default()
        contractor = CompanyInfo.objects.get_our_company_info()
        details = '\n'.join(['%s:%s' % (k, v) for k, v in invoice.items()])
        currCredit = processCredit(cinfo, -price, currency, details,
                                   contractor.bankaccount)

        mailContent = render_to_string('vpnadmin/infoMail.html', {
            'invoice': invoice,
            'state': currCredit,
            'billURL': billURL,
            'price': price,
            'cinfo': cinfo,
            'domain': Site.objects.get_current(),
        })
        subject = ugettext('phone service info')
        cinfo.user.email_user(subject, mailContent)


def processParsedData(parsed):
    invoices = []
    for telnum, info in parsed.items():
        try:
            inv = _processParsedRec(telnum, info)
        except Exception, e:
            logging.exception(e)
        invoices.append(inv)
    return invoices


def _processParsedRec(telnum, info):
    cinfo = CompanyInfo.objects.get(phone=telnum)
    psi = PhoneServiceInfo.objects.get(user=cinfo.user)

    (inVPN, outVPN, smsCount, cInfo, aboveFreeMins,  # @UnusedVariable
     phoneInfo, extra, vpnSmsCount, smsOver) = info  # @UnusedVariable

    outsideVPN = _convertToMinutes(outVPN)
    insideVPN = _convertToMinutes(inVPN)
    minsOver = outsideVPN - psi.minutes

    invoice = {
        _('freeMins') + '(%i min)' % psi.minutes: psi.minutes,
        _('inVPN') + '(%i min)' % insideVPN: 0,
        _('free SMS') + '(%i ks)' % psi.smsCount: 0,
        _('sms in vpn') + '(%i ks)' % vpnSmsCount: 0
    }
    if minsOver > 0:
        p = minsOver * MINUTE_PRICE
        invoice[_('extraMinutes') + '(%i min)' % minsOver] = p
    if smsOver > 0:
        p = smsOver * SMS_PRICE
        invoice[_('extraSMS') + '(%i ks)' % smsOver] = p

    if PROCESSING_FEE:
        invoice[_('processing fee')] = PROCESSING_FEE

    invoice.update(extra)

    return (invoice, cinfo)


def _convertToTimeDelta(time):
    parts = time.split(':')
    return datetime.timedelta(hours=int(parts[0]),
        minutes=int(parts[1]), seconds=int(parts[2]))


def _convertToMinutes(time):
    return (time.days * 24 * 60) + (time.seconds / 60)
