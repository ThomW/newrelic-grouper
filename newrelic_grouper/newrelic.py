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
import ConfigParser
import exceptions
import json
import os
import string
import sys
import time
import urllib2
import xmltodict
import re
import retry
from subprocess import Popen, PIPE

class NRGrouper:

    def __init__(self, conf='/etc/nrgrouper.conf'):

        self.hostname = os.uname()[1]
        self.json_data = {}     #a construct to hold the json call data as we build it
        self.first_run = True   #this is set to False after the first run function is called

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
            self.duration = config.getint('plugin', 'duration')
            self.guid = config.get('plugin', 'guid')
            self.name = config.get('plugin', 'name')
            self.version = config.get('plugin','version')
            self.nrhost = config.get('instance', 'host')
            self.nrport = config.get('instance', 'port')            
            self.nrssl = config.getboolean('instance', 'ssl')
            self.nrfilter = config.get('instance', 'filter')
            self.nrfilterkey = config.get('instance', 'filter_key')
 
            # Let config file override instance "name" in New Relic
            if config.has_option('instance', 'name'):
                self.nrname = config.get('instance', 'name')
                # If it's empty/blank, use Jamie's "parse hostname" thing.
                if self.nrname is None or self.nrname.strip() == "":
                    self.nrname = self._parse_hostname()
            # If not there, use Jamie's "parse hostname" thing.
            else:
                self.nrname = self._parse_hostname()
            
            # host and port now optional
            if self.nrhost is None:
                self.nrhost = 'api.newrelic.com'
            if self.nrport is None:
                self.nrport = 443  
            self.nruri = "%s:%s" % (self.nrhost, self.nrport)
 
            #create a dictionary to hold the various data metrics.
            self.metric_data = {}

            if config.getboolean('plugin','enable_all') == True:
                self.enable_servers = True
            else:
                self.enable_servers = config.getboolean('plugin', 'enable_servers')

            self._build_agent_stanza()
            
            if self.nrssl:
                self.nrurl = "https://%s:%s/v2" % (self.nrhost, self.nrport)
            else:
                self.nrurl = "http://%s:%s/v2" % (self.nrhost, self.nrport)

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

    def _build_component_stanza(self):
        '''this will build the 'component' stanza for the new relic json call'''
        c_list = []
        c_dict = {}
        if (self.nrname is not None):
            c_dict['name'] = self.nrname
        else:
            c_dict['name'] = 'My Servers'
        c_dict['guid'] = self.guid
        c_dict['duration'] = self.duration

        #always get the sys information
        #self._get_sys_info()
        
        if self.enable_servers:
            self.get_details('server', 'filter['+self.nrfilterkey+']='+self.nrfilter)

        c_dict['metrics'] = self.metric_data
        c_list.append(c_dict)

        self.json_data['components'] = c_list
        
    def _prep_first_run(self):
        '''this will prime the needed buffers to present valid data when math is needed'''

        # then we sleep so the math represents 1 minute intervals when we do it next
        # time.sleep(60)
        self.first_run = False
        if self.debug:
            print "The pump is primed"
        return True

    def _reset_json_data(self):
        '''this will 'reset' the json data structure and prepare for the next call. It does this by mimicing what happens in __init__'''
        self.metric_data = {}
        self.json_data = {}
        self._build_agent_stanza()

    def add_to_newrelic(self):
        '''this will glue it all together into a json request and execute'''
        if self.first_run:
            self._prep_first_run()  #prime the data buffers if it's the first loop

        self._build_component_stanza()  #get the data added up
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
            #response = opener.open(request, json.dumps(self.json_data))
            
            if self.debug:
                print request.get_full_url()
                print response.getcode()
                print json.dumps(self.json_data)
                sys.stdout.flush()
            response.close()
        
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
        
        self._reset_json_data()

    def execute_rest(self, resturl, resttype, filter=None):
        response = None
        if filter is not None:
           requrl = "%s/%s.%s?%s" % (self.nrurl, resturl, resttype, filter)
        else:
           requrl = "%s/%s.%s" % (self.nrurl, resturl, resttype)            
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
                print request.get_full_url()
                print response.getcode()
                print results
                sys.stdout.flush()
            response.close()
            return results       
        except IOError, e:
            self.output_error(request, e)          
        return

    def get_details(self, category, filter=None):
        the_deets = self.execute_rest(category+'s', 'json', filter)
        if the_deets is not None:
            print the_deets
            for deet in the_deets[category+'s']:
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
