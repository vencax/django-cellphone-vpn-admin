
from django.conf.urls import patterns, url
import views

urlpatterns = patterns('',
    url(r'^$', views.UploadBillView.as_view(), name='inputForm'),
    url(r'^process/$', views.ProcessBillView.as_view(), name='processForm'),
)
