from setuptools import setup, find_packages

print find_packages()

setup(
    name='vpn-admin',
    version='0.1',
    description='Cellphone VPN network admin.',
    author='Vaclav Klecanda',
    author_email='vencax77@gmail.com',
    url='vxk.cz',
    packages=find_packages(),
    include_package_data=True,
)
