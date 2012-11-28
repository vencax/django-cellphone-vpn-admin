#coding=utf-8
from django.core.management.base import BaseCommand
import logging
import csv
from django.db.transaction import commit_on_success
import unicodedata
from invoices.models import CompanyInfo
from django.contrib.auth.models import User
from vpnadmin.models import PhoneServiceInfo


def make_username_string(input_str):
    nkfd_form = unicodedata.normalize('NFKD', unicode(input_str))
    uname = u''.join([c for c in nkfd_form if not unicodedata.combining(c)])
    uname = uname.replace(' ', '')
    return uname.lower()


class Command(BaseCommand):

    help = u'load data from CSV'  # @ReservedAssignment

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO)
        logging.info('Ensure you process utf-8 encoded file ...')
        reader = csv.reader(open(args[0], 'rb'), delimiter=',')

        headers = None
        for row in reader:
            try:
                if headers:
                    self.process_row(row, headers)
                else:
                    headers = self.readHeaders(row)
            except Exception, e:
                logging.exception(e)

    @commit_on_success
    def process_row(self, row, headers):

        name = self._extractVal('Jméno', row, headers)
        logging.info('Processing: %s' % name)

        email = self._extractVal('E-mail', row, headers)
        telnum = int(self._extractVal('Číslo', row, headers).replace(' ', ''))
        ico = self._extractVal('pripadne ICO', row, headers)
        dic = self._extractVal('pripadne DIC', row, headers)
        accountNum = self._extractVal('CISLO UCTU', row, headers)
        freeMinutes = int(self._extractVal('Min.', row, headers))
        internet = self._extractVal('Int.', row, headers) == '3GB'

        user = self._processUser(name, email)
        self._processCompanyInfo(telnum, ico, dic, accountNum, user)
        self._processPhoneInfo(user, freeMinutes, internet)

    def _processUser(self, name, email):
        try:
            uname = make_username_string(name).replace(',', '_').\
                replace('.', '').lower()
        except UnicodeDecodeError:
            uname = email.split('@')[0]

        try:
            user = User.objects.get(username=uname, email=email)
        except User.DoesNotExist:
            parts = name.split(' ')
            surname, forname = parts[0], ' '.join(parts[1:])
            user = User(username=uname, email=email,
                        first_name=forname, last_name=surname)
            user.save()

        return user

    def _processCompanyInfo(self, telnum, ico, dic, account, user):
        try:
            ci = CompanyInfo.objects.get(user=user)
        except CompanyInfo.DoesNotExist:
            ci = CompanyInfo(user=user)

        ci.bankaccount = account
        ci.inum = ico
        ci.tinum = dic
        ci.phone = telnum

        ci.save()

    def _processPhoneInfo(self, user, freeMinutes, internet):
        try:
            pi = PhoneServiceInfo.objects.get(user=user)
        except PhoneServiceInfo.DoesNotExist:
            pi = PhoneServiceInfo(user=user)

        pi.minutes = freeMinutes
        pi.internet = internet
        pi.save()

    def readHeaders(self, row):
        headers = {}
        cntr = 0
        for h in row:
            headers[h] = cntr
            cntr += 1
        return headers

    def _extractVal(self, key, row, headers):
        val = row[headers[key]]
        try:
            return val.decode('utf-8')
        except UnicodeDecodeError:
            return val
        except UnicodeEncodeError:
            return val
