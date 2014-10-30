# New Relic Grouper plugin #

Description: Allows server metrics to be collected from any servers within in an account and group that data under a plugin dashboard. Can be modified in theory to group any metrics being reported to New Relic that are available through the REST API (https://docs.newrelic.com/docs/features/getting-started-with-the-new-relic-rest-api)

In addition to the Grouper functionality, this version also sends the server metrics to NewRelic Insights as an Event, so that server metrics can be used in Insight's Dashboards as well.

## How to use it: ##

The application installs itself as a daemon, and to install and start the application, run:

    python setup.py install


## Debugging ##

If you're testing the application from the Python shell, it's easy to run by executing the following
from the Python shell: 

```
from newrelic_grouper.newrelic import NRGrouper
g = NRGrouper('./nrgrouper.conf')
g.run()
```

Installation
------------
* RPM
    * Dowload the source and execute:

    ```
    python setup.py sdist_rpm
    cd dist/
    rpm -ivh <RPM You Just Made>.rpm / yum install <RPM You Just Made>.rpm
    ```

    *Obviously you only have to use rpm OR yum (not both), and you only have to make the RPM for each architecture you're using.

* Source Distribution
    * Download the source and execute:

    ```
    python setup.py sdist
    cd dist/
    tar zxf <The Tarball>
    cd <The Directory you just unzipped>
    python setup.py install
    ```

    * Obviously you can move that tarball around after creating it once.
