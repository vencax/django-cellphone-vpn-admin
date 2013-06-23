'''
Created on May 30, 2012

@author: vencax
'''
import re

pattern = '(?P<n1>[0-9]{3}) (?P<n2>[0-9]{3}) (?P<n3>[0-9]{3}) \
(?P<price>[0-9]{1,}),(?P<pricepart>[0-9]{2})'


def parseBill(data):
    parsed = []
    for occ in re.finditer(pattern, data):
        telnum = int(occ.group('n1') + occ.group('n2') + occ.group('n3'))
        price = float('%s.%s' % (occ.group('price'), occ.group('pricepart')))
        parsed.append((telnum, price))
    return parsed

if __name__ == '__main__':
    testdata = """
723 244 366 11,69
724 692 035 11,59
777 021 927 3,40
777 756 134 1,23
777 769 822 26,20
777 756 132 17,01
777 756 135 86,62
777 756 142 0,00
777 756 151 0,00
777 769 821 0,00
777 756 141 2,27
777 756 172 0,00
777 756 150 4,23
777 769 848 1,13
777 769 827 16,70
775 313 097 73,64
777 662 578 3,06
775 644 723 11,94
607 932 020 8,71
775 072 024 34,05
773 131 593 1,76
775 151 099 13,70
774 977 924 49,60
774 205 570 56,32
776 673 435 20,26
    """
    print parseBill(testdata)
