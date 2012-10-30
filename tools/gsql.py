#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2012 Brailcom, o.p.s.
#
# COPYRIGHT NOTICE
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import optparse
import sys

import pytis.extensions.gensqlalchemy

USAGE = """usage: %prog [ OPTIONS ] SPECIFICATION-FILE"""

def parse_options():
    parser = optparse.OptionParser(usage=USAGE)
    parser.add_option("--limit", default=None, action="store", dest="regexp",
                      help="output specifications matching and dependent on REGEXP")
    parser.add_option("--views", action="store_true", dest="views",
                      help="limit output to views")
    parser.add_option("--functions", action="store_true", dest="functions",
                      help="limit output to functions")
    options, args = parser.parse_args(args=sys.argv[1:])
    if len(args) != 1:
        parser.print_help()
        sys.exit(1)
    return options, args[0]

def run():
    options, file_name = parse_options()
    pytis.extensions.gensqlalchemy.gsql_file(file_name, regexp=options.regexp,
                                             views=options.views, functions=options.functions)

if __name__ == '__main__':
    run()
