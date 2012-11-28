

from creditservices.signals import new_credit_arrived
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _

from .signals import on_new_credit


class PhoneServiceInfo(models.Model):
    """
    """

    user = models.ForeignKey(User, unique=True,
                             related_name='phoneserviceinfo')
    minutes = models.IntegerField(_('free minutes'))
    internet = models.IntegerField(_('has internet'), default=0)

    def __unicode__(self):
        return 'PhoneServiceInfo of %s' % self.user.get_full_name()

    def phone(self):
        return self.user.companyinfo.phone
    phone.short_description = _('phone')

new_credit_arrived.connect(on_new_credit)
