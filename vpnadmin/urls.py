
from django.conf.urls import patterns, url
from .views import UploadBillView, ProcessBillView

urlpatterns = patterns('',
    url(r'^$', UploadBillView.as_view(), name='inputForm'),
    url(r'^process/', ProcessBillView.as_view(), name='processForm'),
)