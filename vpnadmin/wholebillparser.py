# coding=UTF-8
'''
Created on May 30, 2012

@author: vencax
'''
import re

personInfoBeginRe = u'Telefonní èíslo (?P<tel>[0-9]{3} [0-9]{3} [0-9]{3}) VPN firma neomezenì - èlen'
timeInVPNRe = u'Celkem za Skupinová volání [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})'
timOutsideVPNRe = u'Celkem za Hlasové sluby [0-9]{1,} (?P<time>[0-9]{2}:[0-9]{2}:[0-9]{2})'
smsRe = u'Celkem za SMS sluby (?P<sms>[0-9]{1,})'
personInfoEndRe = u'Celkem za sluby Vodafone'

class WholeBillParser(object):
    def __init__(self):
        self._inPersonInfo = False
        self._personInfo = ''
        
    def parse(self, parsedfile):
        parsed = {}
        for line in parsedfile:
            line = unicode(line)
            if self._inPersonInfo is True:
                s = re.search(personInfoEndRe, line)
                if s:
                    self._inPersonInfo = False
                    parsed[self._currTel] = (self._timeInVPN, self._timeOutsideVPN, self._smsCount)
                    continue                
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
            else:
                found = re.search(personInfoBeginRe, line)
                if found:
                    self._currTel = int(found.group('tel').replace(' ', ''))
                    self._inPersonInfo = True
        return parsed

if __name__ == '__main__':
    import os
    p = WholeBillParser()
    with open(os.path.join(os.path.dirname(__file__), 'kokot.txt')) as f:
        result = p.parse(f)
    i = 1
    for tel, info in result.items():
        print '%i: %s = %s' % (i, tel, info)
        i += 1