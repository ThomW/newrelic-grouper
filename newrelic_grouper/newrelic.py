#!/usr/bin/env python
# -*- coding: iso-8859-15 -*-
# Copyright (C) 2013  Seth Schwartzman (seth.schwartzman@gmail.com) and Jamie Duncan (jamie.e.duncan@gmail.com)

# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

# File Name : newrelic.py
# Creation Date : 11-06-2013
# Created By : Jamie Duncan
# Repurposed By : Seth Schwartzman
# Last Modified : Sun 17 Nov 2013 10:10:10 AM EST
# Purpose : Metric Grouper Plugin for New Relic

import ast
import base64
from collections import defaultdict, OrderedDict
import ConfigParser
import exceptions
import json
import os
from pprint import pprint
import string
import sys
import time
import urllib2
import xmltodict
import re
import retry
from subprocess import Popen, PIPE

def tree(): 
    return defaultdict(tree)

class NRGrouper:

    def __init__(self, conf='/etc/nrgrouper.conf'):

        self.hostname = os.uname()[1]
        self.json_data = {}     #a construct to hold the json call data as we build it

        try:
            self.config_file = conf
            config = ConfigParser.RawConfigParser()
            config.read(self.config_file)
            
            self.debug = config.getboolean('newrelic','debug')    
            self.enable_proxy = config.getboolean('newrelic','enable_proxy')
            if self.enable_proxy:
                self.http_proxy_url = config.get('newrelic','http_proxy_url')
                self.http_proxy_port = config.get('newrelic','http_proxy_port')
                self.http_proxy_type = config.get('newrelic','http_proxy_type')
            self.api_key = config.get('newrelic', 'api_key')
            self.license_key = config.get('newrelic', 'key')
            self.api_url = config.get('newrelic', 'url')

            self.insights_account_id = config.get('Insights', 'account_id')
            self.insights_api_key = config.get('Insights', 'api_key')
            self.insights_url = config.get('Insights', 'url')
            self.insights_event_type = config.get('Insights', 'event_type')

            self.duration = config.getint('plugin', 'duration')
            self.guid = config.get('plugin', 'guid')
            self.name = config.get('plugin', 'name')
            self.version = config.get('plugin','version')
            
            self.instances = tree()
            for section in config.sections():
                if str(section).find('instance') == -1:
                    continue
                    
                nrname = config.get(section, 'name')
                self.instances[nrname]['nrname'] = nrname
                self.instances[nrname]['nrhost'] = config.get(section, 'host')
                if self.instances[nrname]['nrhost'] is None:
                    self.instances[nrname]['nrhost'] = 'api.newrelic.com'
                self.instances[nrname]['nrport'] = config.get(section, 'port')
                if self.instances[nrname]['nrport'] is None:
                    self.instances[nrname]['nrport'] = 443
                self.instances[nrname]['nrssl'] = config.getboolean(section, 'ssl')             
                self.instances[nrname]['nrfilter'] = config.get(section, 'filter')
                self.instances[nrname]['nrfilterkey'] = config.get(section, 'filter_key')
                self.instances[nrname]['nruri'] = "%s:%s" % (self.instances[nrname]['nrhost'], self.instances[nrname]['nrport'])
                if self.instances[nrname]['nrssl']:
                    self.instances[nrname]['nrurl'] = "https://%s:%s/v2" % (self.instances[nrname]['nrhost'], self.instances[nrname]['nrport'])
                else:
                    self.instances[nrname]['nrurl'] = "http://%s:%s/v2" % (self.instances[nrname]['nrhost'], self.instances[nrname]['nrport'])
            
            #create a dictionary to hold the various data metrics.
            self.metric_data = {}

            if config.getboolean('plugin','enable_all') == True:
                self.enable_servers = True
            else:
                self.enable_servers = config.getboolean('plugin', 'enable_servers')

            self._build_agent_stanza()
            

        except:
            print "Cannot Open Config File", sys.exc_info()[0]
            raise

    def _build_agent_stanza(self):
        '''this will build the 'agent' stanza of the new relic json call'''
        values = {}
        values['host'] = self.hostname
        values['pid'] = 1000
        values['version'] = self.version
        self.json_data['agent'] = values

    def _build_component_stanza(self, instance):
        #pprint(instance)
        '''this will build the 'component' stanza for the new relic json call'''
        c_list = []
        c_dict = {}
        if (instance['nrname'] is not None):
            c_dict['name'] = instance['nrname']
        else:
            c_dict['name'] = 'My Servers'
        c_dict['guid'] = self.guid
        c_dict['duration'] = self.duration

        #always get the sys information
        #self._get_sys_info()
        
        if self.enable_servers:
            self.get_details(instance['nrurl'], 'server', 'filter['+instance['nrfilterkey']+']='+instance['nrfilter'])

        c_dict['metrics'] = self.metric_data
        c_list.append(c_dict)

        self.json_data['components'] = c_list

    def run(self):
        """
        This is the infinite loop that's responsible for keeping the application alive
        """
        # INFINITE LOOP
        while True:

            # Capture start time of this iteration of the main loop
            start_time = time.time()

            # Update all instances
            for instance in self.instances:
                self.add_to_newrelic(instance)

            # Calculate the amount of time passed, and the amount of time that should be spent sleeping
            duration = time.time() - start_time
            sleep_seconds = 0
            if duration <= 60:
                sleep_seconds = 60 - duration

            if self.debug:
                print 'Last loop took {duration} seconds. Sleeping for {sleep_seconds} seconds'.format(duration=duration, sleep_seconds=sleep_seconds)

            time.sleep(sleep_seconds)

        
    def add_to_newrelic(self, instance):
        """
        * Query data from New Relic APM
        * Build response
        * Send response for Grouper Plugin
        * Send response to Insights
        """

        # Reset variables
        self.newrelic_data = {}
        self.metric_data = {}
        self.json_data = {}
        self._build_agent_stanza()

        request_complete = False

        # Do a request to retrieve data from New Relic,
        # and format data into something we can feed back as
        # part of grouper.  Data is formatted and stored in self.json_data.
        self._build_component_stanza(self.instances[instance])

        try:
            if self.enable_proxy:
                proxy_handler = urllib2.ProxyHandler({'%s' % self.http_proxy_type : '%s:%s' % (self.http_proxy_url, self.http_proxy_port)})
                opener = urllib2.build_opener(proxy_handler)
            else:
                opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler())
            request = urllib2.Request(self.api_url)
            request.add_header("X-License-Key", self.license_key)
            request.add_header("Content-Type","application/json")
            request.add_header("Accept","application/json")
            
            response = self.opener_with_retry(opener, request, json.dumps(self.json_data))
            
            if self.debug:
                print request.get_full_url()
                print response.getcode()
                print json.dumps(self.json_data)
                sys.stdout.flush()
            response.close()

            print 'returned from opener_with_retry'

            request_complete = True

            print 'request_complete = {0}'.format(request_complete)

        except urllib2.HTTPError, err:
            if self.debug:
                print request.get_full_url()
                print err.code
                print json.dumps(self.json_data)
                sys.stderr.flush()
                sys.stdout.flush()
            pass    #i know, i don't like it either, but we don't want a single failed connection to break the loop.
        
        except IOError, err:
            if self.debug:
                print request.get_full_url()
                print err   #this error will kick if you lose DNS resolution briefly. We'll keep trying.
                sys.stderr.flush()
                sys.stdout.flush()
            pass

        # If the above request was completed successfully, fire off the Insights event
        # to format and send an event to Insights
        if request_complete:
            self.post_insights_event(self.instances[instance])


    def post_insights_event(self, active_instance):
        """
        Take the current metric_data and create an Insights event
        """

        """
        Sample of self.metric_data which is used to build data for Insights event

        {
            u'links':
            {
                u'server.alert_policy': u'/v2/alert_policies/{alert_policy_id}'
            },
            u'servers':
            [
                {
                    u'name': u'LMNOpc',
                    u'links':
                    {
                        u'alert_policy': 288120
                    },
                    u'reporting': True,
                    u'host': u'(none)',
                    u'summary':
                    {
                        u'memory_used': 288358400,
                        u'disk_io': 0.01,
                        u'fullest_disk': 30.8,
                        u'memory_total': 2088763392,
                        u'fullest_disk_free': 11119000000,
                        u'cpu_stolen': 0.02,
                        u'memory': 13.8,
                        u'cpu': 1.55
                    },
                    u'health_status': u'gray',
                    u'last_reported_at': u'2014-09-25T15:19:39+00:00',
                    u'id': 11188319,
                    u'account_id': 755776
                }
            ]
        }
        """

        # Build Insights event data structure
        # See: https://docs.newrelic.com/docs/insights/new-relic-insights/adding-querying-data/inserting-custom-events#json-format
        insights_event = []
        for server in self.newrelic_data['servers']:
            event = OrderedDict([
                    ('eventType', self.insights_event_type),
                    ('groupName', active_instance['nrname']),
                    ('serverName', server['name'])
                ])
            for key in server['summary']:
                event[key] = server['summary'][key]
            insights_event.append(event)

        # Blast data to Insights
        try:
            if self.enable_proxy:
                proxy_handler = urllib2.ProxyHandler({'%s' % self.http_proxy_type : '%s:%s' % (self.http_proxy_url, self.http_proxy_port)})
                opener = urllib2.build_opener(proxy_handler)
            else:
                opener = urllib2.build_opener(urllib2.HTTPHandler(), urllib2.HTTPSHandler())

            # Adding data here rather than passing along as parameter to opener_with_retry so that the request is POST'd
            # See: https://docs.python.org/2/library/urllib2.html#urllib2.Request
            request = urllib2.Request(self.insights_url.format(account_id = self.insights_account_id), json.dumps(insights_event))
            request.add_header("X-Insert-Key", self.insights_api_key)
            request.add_header("Content-Type","application/json")
            request.add_header("Accept","application/json")

            response = self.opener_with_retry(opener, request)

            if self.debug:
                print request.get_full_url()
                print response.getcode()
                print json.dumps(insights_event)
                sys.stdout.flush()

            response.close()

        except urllib2.HTTPError, err:
            if self.debug:
                print request.get_full_url()
                print err.code
                print json.dumps(insights_event)
                sys.stderr.flush()
                sys.stdout.flush()
            pass    #i know, i don't like it either, but we don't want a single failed connection to break the loop.
        
        except IOError, err:
            if self.debug:
                print request.get_full_url()
                print err   #this error will kick if you lose DNS resolution briefly. We'll keep trying.
                sys.stderr.flush()
                sys.stdout.flush()
            pass

    def execute_rest(self, nrurl, resturl, resttype, filter=None):
        response = None
        if filter is not None:
           requrl = "%s/%s.%s?%s" % (nrurl, resturl, resttype, filter)
        else:
           requrl = "%s/%s.%s" % (nrurl, resturl, resttype)            
        request = urllib2.Request(requrl)
        request.add_header("Content-Type","application/"+resttype)
        request.add_header("Accept","application/"+resttype) 
        request.add_header("X-Api-Key", self.api_key)
        
        try:
            response = urllib2.urlopen(request)
        except urllib2.HTTPError, e:
            self.output_error(request, e)
            return
        except IOError, e:
            self.output_error(request, e)
            return

        try:
            if response is None:
                return # No response to parse.
            if resttype == 'json':
                results = json.loads(response.read())
            elif resttype == 'xml':
                results = xmltodict.parse(response.read())
            if self.debug:
                print 'URL: ' + request.get_full_url()
                print response.getcode()
                print 'RESULTS'
                print results
                print ''
                sys.stdout.flush()
            response.close()
            return results       
        except IOError, e:
            self.output_error(request, e)          
        return

    def get_details(self, nrurl, category, filter=None):
        self.newrelic_data = self.execute_rest(nrurl, category+'s', 'json', filter)
        if self.newrelic_data is not None:
            print self.newrelic_data
            for deet in self.newrelic_data[category+'s']:
                self.print_results(deet, deet['name'])

    def print_results(self, data, prefix):
        if data is None:
            return
        for (path, dicts, items) in self.walk_results(data):
            for key,value in items:
                try:
                    metric_value = float(value)
                    path_str = str(path)
                    key_str = str(key)
                except:
                    continue
                metric_name = 'Component/'+prefix+path_str+key_str
                if self.debug:
                    print '%s = %s' % (metric_name, metric_value)
                self.metric_data[metric_name] = metric_value
                del metric_value
                del metric_name
        if self.debug:
            sys.stdout.flush()

    @retry.retry(urllib2.URLError, tries=3, timeout_secs=1.0)
    def urlopen_with_retry(self, request):
        return urllib2.urlopen(request)
   
    @retry.retry(urllib2.URLError, tries=3, timeout_secs=1.0)
    def opener_with_retry(self, opener, request, payload=None):
        if payload is None:
            return opener.open(request)
        else:
            return opener.open(request, payload)
    
    def output_error(self, request, e):
        if self.debug:
            print 'Request URL: %s' % (request.get_full_url())
            print 'Error: %s' % (e)
            if e.code is not None:
                print 'Error Code: %s' % (e.code)
            sys.stderr.flush()
            sys.stdout.flush()
        return             
         
    def walk_results(self, data):
        nested_keys = tuple(key for key in data.keys() if isinstance(data[key],dict))
        items = tuple((key,data[key]) for key in data.keys() if key not in nested_keys)
        yield ('/', [(key,data[key]) for key in nested_keys], items)
        for key in nested_keys:
            for result in self.walk_results(data[key]):
                result = ('/%s' % key + result[0], result[1], result[2])
                yield result
