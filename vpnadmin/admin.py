'''
Created on Jun 7, 2012

@author: vencax
'''
from django.contrib import admin

from .models import PhoneServiceInfo

class PhoneServiceInfoAdmin(admin.ModelAdmin):
    list_display = ('user', 'minutes', 'internet')
    list_filter = ('internet', )
    search_fields = ('user__last_name', )
    
admin.site.register(PhoneServiceInfo, PhoneServiceInfoAdmin)