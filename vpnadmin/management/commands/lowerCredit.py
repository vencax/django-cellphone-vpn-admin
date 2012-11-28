'''
Created on Dec 29, 2011

@author: vencax
'''
import logging
from invoices.models import CompanyInfo
from django.core.management.base import BaseCommand
from valueladder.models import Thing
from creditservices.signals import processCredit
from optparse import make_option
from django.utils.translation import activate
from django.conf import settings


class Command(BaseCommand):
    help = 'lowers credit with given value to user with \
given phone num'  # @ReservedAssignment

    option_list = BaseCommand.option_list + (
        make_option('--num', help='phone num as integer'),
        make_option('--value', help='new credit value'),
        make_option('--currency', help='currency code'),
    )

    def handle(self, *args, **options):
        activate(settings.LANGUAGE_CODE)
        logging.basicConfig()

        companyInfo = CompanyInfo.objects.get(phone=options['num'])
        if options['currency']:
            currency = Thing.objects.get(code=options['currency'])
        else:
            currency = Thing.objects.get_default()

        processCredit(companyInfo, -int(options['value']),
                      currency, 'manual lower credit')
