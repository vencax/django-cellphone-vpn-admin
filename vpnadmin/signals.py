'''
Created on Jun 25, 2012

@author: vencax
'''
from invoices.models import CompanyInfo, Invoice, Item
from django.utils.translation import ugettext

def on_new_credit(sender, vs, ss, amount, creditInfo, **kwargs):
    """ Creates invoice with credit """
    companyInfo = CompanyInfo.objects.get(user__id=int(vs))
    invoice = Invoice(subscriber=companyInfo, paid=True)
    invoice.save()
    invoice.items.add(Item(price=amount, 
                           name=ugettext('Phone services credit')))
    invoice.send()