'''
Created on Jun 7, 2012

@author: vencax
'''
from django.contrib import admin

from .models import PhoneServiceInfo


class PhoneServiceInfoAdmin(admin.ModelAdmin):
    list_display = ('user', 'phone', 'minutes', 'internet')
    list_filter = ('internet', )
    search_fields = ('user__last_name', 'user__companyinfo__phone')


admin.site.register(PhoneServiceInfo, PhoneServiceInfoAdmin)
