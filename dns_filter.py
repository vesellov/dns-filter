#!/usr/bin/env python

"""
Usage: python3 dns_filter.py --verbose --port 10053 --to xyz.net --regexp "^abcd.+?.com$"

Custom forwarding DNS server.
Redirects input traffic matching given regular expression to a given host.

Options:
    -h, --help            show this help message and exit
    -v, --verbose         log incoming requests to the console
    -p PORT, --port=PORT  DNS server port number
    -t TO, --to=TO        destination CNAME
    -r REGEXP, --regexp=REGEXP
                          regular expression to be checked
    -i INTERFACE, --interface=INTERFACE
                          interface IP to listen on

Example:
    $ python3 -m pip install twisted
    $ python3 dns_filter.py --verbose --port=10053 --to=xyz.net --regexp="^abcd.+?.com$"

    $ dig -p 10053 @localhost abcd-example.com CNAME +short
    xyz.net

Based on:
    https://twistedmatrix.com/documents/16.5.0/names/howto/custom-server.html

"""

import sys

if sys.version_info[0] == 3:
    binary_type = bytes
else:
    binary_type = str

import logging
import optparse
import re

from twisted.internet import reactor, defer
from twisted.names import dns, error, server


class DynamicResolver(object):
    """
    A resolver which calculates the answers to certain queries based on the
    query type and name.
    """

    def __init__(self, to, regexp, verbose=False):
        self.to = to
        self.regexp = re.compile(regexp, flags=re.IGNORECASE) if regexp else None
        self.verbose = verbose

    def _dynamicResponseRequired(self, name):
        """
        Check the query to determine if a dynamic response is required.
        """
        if isinstance(name, binary_type):
            name = name.decode(encoding='utf-8')
        if self.regexp and self.regexp.match(name):
            if self.verbose:
                logging.info('%r will be redirected', name)
            return True
        if self.verbose:
            logging.info('%r is not matching', name)
        return False

    def _doDynamicResponse(self, query):
        """
        Calculate the response to a query.
        """
        name = query.name.name
        answers = [
            dns.RRHeader(
                name=name,
                type=dns.CNAME,
                payload=dns.Record_CNAME(
                    name=self.to,
                ),
            ),
            dns.RRHeader(
                name=name,
                type=dns.SOA,
                payload=dns.Record_SOA(
                    serial=2018101700,
                    refresh=10800,
                    minimum=86400,
                    expire=604800,
                    retry=2000,
                ),
            ),
            dns.RRHeader(
                name=name,
                type=dns.NS,
                payload=dns.Record_NS(
                    name='work.offshore.ai.',
                ),
            ),
            dns.RRHeader(
                name=name,
                type=dns.NS,
                payload=dns.Record_NS(
                    name='auction.whois.ai.',
                ),
            ),
        ]
        authority = []
        additional = []
        return answers, authority, additional

    def query(self, query, timeout=None):
        """
        Check if the query should be answered dynamically, otherwise dispatch to
        the fallback resolver.
        """
        if self._dynamicResponseRequired(query.name.name):
            return defer.succeed(self._doDynamicResponse(query))
        return defer.fail(error.DomainError())

    def lookupAllRecords(self, name, timeout=None):
        if self._dynamicResponseRequired(name):
            query = dns.Query(name=name, type=dns.ALL_RECORDS, cls=dns.IN)
            return defer.succeed(self._doDynamicResponse(query))
        return defer.fail(error.DomainError())


def main():
    """
    Run the server.
    """
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    p = optparse.OptionParser(
        description='Custom DNS server. Redirects input traffic matching given regular expression to given host.',
        prog='dns_filter',
        usage='python dns_filter.py --port 10053 --to xyz.net --regexp "^abcd.+?.com$"'
    )
    p.add_option('--verbose', '-v', help="log incoming requests to the console", default=False, action="store_true")
    p.add_option('--port', '-p', help="DNS server port number",  default=10053, type='int')
    p.add_option('--to', '-t', help="destination CNAME", default="127.0.0.1")
    p.add_option('--regexp', '-r', help="regular expression to be checked")
    p.add_option('--interface', '-i', help="interface IP to listen on", default="")
    options, arguments = p.parse_args()

    factory = server.DNSServerFactory(
        clients=[
            DynamicResolver(
                to=options.to,
                regexp=options.regexp,
                verbose=options.verbose,
            ),
        ],
    )

    protocol = dns.DNSDatagramProtocol(controller=factory)

    reactor.listenUDP(options.port, protocol, interface=options.interface)
    reactor.listenTCP(options.port, factory, interface=options.interface)

    reactor.run()


if __name__ == '__main__':
    raise SystemExit(main())
