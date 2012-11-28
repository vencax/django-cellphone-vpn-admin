# coding=UTF-8
'''
Created on May 30, 2012

@author: vencax
'''
import re

personInfoBeginRe = u'Telefonní èíslo (?P<tel>[0-9]{3} [0-9]{3} [0-9]{3}) '
timeInVPNRe = u'Celkem za Skupinová volání [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})'
timOutsideVPNRe = u'Celkem za Hlasové sluby [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})'
smsRe = u'Celkem za SMS sluby (?P<sms>[0-9]{1,})'
vpnSMS = u'AU VPN firma neomezenì (?P<sms>[0-9]{1,}) 0,00'
thirrdPartyPay = u'Celkem za Platby tøetím stranám [0-9]{1,} ([0-9]{2}:[0-9]{2}:[0-9]{2} ){0,1}(?P<val>[0-9]{1,},[0-9]{2})'
voiceRoaming = u'Celkem za Roaming - hlasové sluby [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2}) [^ ]{1,} [^ ]{1,} (?P<val>[0-9]{1,},[0-9]{2})'
smsRoaming = u'Celkem za Roaming - SMS [0-9]{1,} [^ ]{1,} [^ ]{1,} (?P<val>[0-9]{1,},[0-9]{2})'
data = u'Celkem za Data (?P<val>[0-9]{1,},[0-9]{2})'
mmsRe = u'Celkem za MMS (?P<val>[0-9]{1,},[0-9]{2})'
personInfoEndRe = u'Celkem za sluby Vodafone'
barevneAInfoLinky = u'AU Barevné a informaèní linky [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2}) [^%]{1,}% (?P<val>[0-9]{1,},[0-9]{2})'

class WholeBillParser(object):
    def __init__(self):
        self._inPersonInfo = False
        self._personInfo = ''
        self._reset()
        
    def parse(self, parsedfile):
        parsed = {}
        for line in parsedfile:
            line = unicode(line)
            
            found = re.search(personInfoBeginRe, line)
            if found:
                if self._currTel:
                    parsed[self._currTel] = (self._timeInVPN, self._timeOutsideVPN, 
                                         self._smsCount, self._extra, self._vpnSmsCount)
                    self._reset()
                self._currTel = int(found.group('tel').replace(' ', ''))
                self._inPersonInfo = True
                continue
            if self._inPersonInfo is True:
                s = re.search(timeInVPNRe, line)
                if s:
                    self._timeInVPN = s.group('time')
                    continue
                s = re.search(timOutsideVPNRe, line)
                if s:
                    self._timeOutsideVPN = s.group('time')
                    continue
                s = re.search(smsRe, line)
                if s:
                    self._smsCount = int(s.group('sms'))
                    continue
                s = re.search(vpnSMS, line)
                if s:
                    self._vpnSmsCount = int(s.group('sms'))
                    continue
                s = re.search(thirrdPartyPay, line)
                if s:
                    self._extra['3rdPartyPay'] = float(s.group('val').replace(',', '.'))
                    continue
                s = re.search(barevneAInfoLinky, line)
                if s:
                    v = float(s.group('val').replace(',', '.'))
                    if v > 0:
                        self._extra['barevneAInfoLinky'] = v 
                    continue
                s = re.search(voiceRoaming, line)
                if s:
                    self._extra['voiceRoaming'] = float(s.group('val').replace(',', '.'))
                    continue
                s = re.search(smsRoaming, line)
                if s:
                    self._extra['smsRoaming'] = float(s.group('val').replace(',', '.'))
                    continue
                s = re.search(data, line)    
                if s:
                    self._extra['data'] = float(s.group('val').replace(',', '.'))
                    continue
                s = re.search(mmsRe, line)    
                if s:
                    self._extra['mms'] = float(s.group('val').replace(',', '.'))
                    continue
                    
        if self._currTel:
            parsed[self._currTel] = (self._timeInVPN, self._timeOutsideVPN, 
                                 self._smsCount, self._extra, self._vpnSmsCount)
                                    
        return parsed
    
    def _reset(self):
        self._currTel = None
        self._timeInVPN = self._timeOutsideVPN = '00:00:00'
        self._smsCount = self._vpnSmsCount = 0
        self._extra = {}

if __name__ == '__main__':
    import os
    p = WholeBillParser()
    with open(os.path.join(os.path.dirname(__file__), 'singlekokot.txt')) as f:
        result = p.parse(f)
    i = 1
    for tel, info in result.items():
        print '%i: %s = %s' % (i, tel, info)
        i += 1