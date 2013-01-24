
from django.db import models
from django.contrib.auth.models import User
from django.utils.translation import ugettext_lazy as _
from creditservices.signals import new_credit_arrived


class PhoneServiceInfo(models.Model):
    """
    """

    user = models.ForeignKey(User, unique=True,
                             related_name='phoneserviceinfo')
    minutes = models.IntegerField(_('free minutes'))
    smsCount = models.IntegerField(_('sms count'))
    internet = models.IntegerField(_('has internet'), default=0)

    def __unicode__(self):
        return 'PhoneServiceInfo of %s' % self.user.get_full_name()

    def phone(self):
        try:
            return self.user.companyinfo.all()[0].phone
        except IndexError:
            return 0
    phone.short_description = _('phone')


from .signals import on_new_credit
new_credit_arrived.connect(on_new_credit)
