#!/usr/bin/env python

# Copyright (C) 2010, 2011, 2015 Brailcom, o.p.s.
#
# COPYRIGHT NOTICE
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Dump Pytis application specifications to STDOUT.
 
Specifications, thier fields and properties are dumped to standard output in a
way, that allows comparing these outputs to detect changes caused by
modifications of specification files or Pytis API changes (or both).

"""

import sys
import re
import getopt
import argparse

import pytis.presentation
import pytis.util

class NullLogger(pytis.util.Logger):
    def log(self, *args, **kwargs):
        pass

OBJID_REGEX = re.compile(r'(object )?at 0x[0-9a-f]+')

def run():
    parser = argparse.ArgumentParser(
        description="Dump Pytis application specifications to STDOUT",
        epilog=("Additionally, you can pass other valid Pytis command line arguments, "
                "such as --dbhost or --dbname to override certain configuration file "
                "options."),
    )
    parser.add_argument('-w', '--wiking', action='store_true',
                        help="Dump a wiking application (Pytis wx application is the default)")
    parser.add_argument('-e', '--exit-on-error', action='store_true',
                        help=("Print traceback and exit when exception occurs. "
                              "By default, the error message is printed to the "
                              "dump output and the program continues."))
    parser.add_argument('-x', '--exclude', nargs='+', metavar='NAME', default=(),
                        help="Name(s) of specification(s) to skip")
    parser.add_argument('-i', '--include', nargs='+', metavar='NAME', default=(),
                        help="Dump only given specification name(s)")
    parser.add_argument('--config', required=True, metavar='PATH',
                        help="Configuration file path")

    args, argv = parser.parse_known_args()
    import config
    try:
        config.add_command_line_options([sys.argv[0], '--config', args.config] + argv)
    except getopt.GetoptError as e:
        parser.print_help()
        sys.exit(1)
    config.log_logger = (NullLogger, (), {})
    import lcg
    lcg.log = lambda *args, **kwargs: None
    if args.wiking:
        import wiking
        wiking.cfg.user_config_file = config.config_file
        config.resolver = wiking.cfg.resolver = wiking.WikingResolver(wiking.cfg.modules)
        config.dbconnections = wiking.cfg.connections
        config.dbconnection = config.option('dbconnection').default()
    resolver = config.resolver
    processed, errors = 0, 0
    if args.include:
        names = args.include
    else:
        if args.wiking:
            base_class = wiking.Module
        else:
            base_class = pytis.presentation.Specification
        names = sorted(name for name, cls in resolver.walk(cls=base_class))
    for name in names:
        if name not in args.exclude:
            try:
                if args.wiking:
                    cls = resolver.wiking_module_cls(name)
                    if not hasattr(cls, 'Spec'):
                        continue
                    module = resolver.wiking_module(name)
                    spec = module.Spec(cls)
                    data = module._data
                else:
                    spec = resolver.specification(name)
                    if not spec.public:
                        continue
                    data_spec = spec.data_spec()
                    data = data_spec.create(dbconnection_spec=config.dbconnection)            
                #print ' ', spec.table
                view_spec = spec.view_spec()
                record = pytis.presentation.PresentedRow(view_spec.fields(), data, None)
                for fid in sorted(record.keys()):
                    t = record.type(fid)
                    f = view_spec.field(fid)
                    attr = (
                        #('label', f.label()),
                        ('not_null', t.not_null()),
                        # We care only about the resulting not_null value which
                        # is printed above, not about type's not_null argument.
                        ('type', (str(t)
                                  .replace(' not_null=True', '')
                                  .replace(' not_null=False', ''))),
                        ('editable', f.editable()),
                        ('computer', f.computer()),
                    )
                    attributes = ' '.join('%s=%s' % (k, v) for k, v in attr if v is not None)
                    print OBJID_REGEX.sub('', '%s.%s %s' % (name, fid, attributes)).encode('utf-8')
                print
            except Exception as e:
                if args.exit_on_error:
                    try:
                        import cgitb
                        tb = cgitb.text(sys.exc_info())
                    except:
                        import traceback
                        tb = "".join(traceback.format_exception(*sys.exc_info())) + "\n"
                    sys.stderr.write(tb)
                    sys.stderr.write("Failed on specification: %s\n\n" % name)
                    sys.exit(1)
                else:
                    print 'ERROR: %s: %s: %r' % (name, e.__class__.__name__, e)
                    errors += 1
            processed += 1
    sys.stderr.write("Processed %d specifications with %d errors%s.\n" %
                     (processed, errors,
                      " (grep output for '^ERROR:' or use --exit-on-error)" if errors else ''))


if __name__ == '__main__':
    run()
