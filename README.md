# New Relic Grouper plugin #

Description: Allows you to collect server metrics from any servers in your account and group that data in a plugin dashboard. Can be modified in theory to group any metrics being reported to New Relic that are available through the REST API (https://docs.newrelic.com/docs/features/getting-started-with-the-new-relic-rest-api)

## How to use it: ##

The application installs itself as a daemon, and to install and start the application, run:

    python setup.py install


## Debugging ##

If you're testing the application from the Python shell, it's easy to run by executing the following
from the Python shell: 

from newrelic_grouper.newrelic import NRGrouper
g = NRGrouper('./nrgrouper.conf')
g.run()
