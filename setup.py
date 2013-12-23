#!/usr/bin/env python

from distutils.core import setup, Extension
import ConfigParser

config = ConfigParser.RawConfigParser()
config.read('nrgrouper.conf')

version = config.get('plugin','version')

setup(
    name='nrgrouper',
    version=version,
    description='New Relic Grouper Plugin',
    author= 'Seth Schwartzman',
    author_email='seth@newrelic.com',
    url='https://github.com/sschwartzman/newrelic-grouper-plugin',
    platform=['Linux'],
    maintainer='Seth Schwartzman',
    maintainer_email = 'seth@newrelic.com',
    long_description='A plugin for New Relic (http://www.newrelic.com)',
    packages=['newrelic_grouper','daemon','daemon.version','lockfile'],
    scripts = ['scripts/nrgrouper'],
    data_files=[
        ('/etc',['nrgrouper.conf']),
        ('/usr/share/doc/nrgrouper-%s'% version, ['README.md','LICENSE','LICENSE-daemon']),
        ('/etc/init.d', ['scripts/nrgrouper-plugin']),
        ],
    )


