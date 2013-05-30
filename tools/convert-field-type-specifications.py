#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys, re, ast, cStringIO, os
from pytis.extensions.ast_unparser import Unparser
from pytis.util import find

TYPE_KWARGS = ('not_null', 'unique', 'constraints', 'minlen', 'maxlen', 'minimum', 'maximum',
               'encrypted', 'precision', 'format', 'mindate', 'maxdate', 'utc',
               'validation_messages', 'inner_type',
               'minsize', 'maxsize', 'formats', 'strength', 'md5', 'verify', 'text',)

def unparse(node):
    x = cStringIO.StringIO()
    Unparser(node, x)
    return x.getvalue()


class Position(object):
    def __init__(self, ln, offset):
        self.ln = ln
        self.offset = offset
    

class Arg(object):
    def __init__(self, lines, kw, previous):
        self.kw = kw
        self.name = kw.arg
        self.value = kw.value
        ln = kw.value.lineno - 1
        offset = kw.value.col_offset
        while lines[ln][offset-1] != '=':
            # First step back up to the keyword argument assignment sign as
            # there may be parens prior to the actual value.
            ln, offset = self._step_back(ln, offset, lines)
        while lines[ln][offset-1] not in ',(':
            # Lookup the end of the previous argument or the beginning paren
            # starting at the beginning of the current argument's value.
            ln, offset = self._step_back(ln, offset, lines)
        if lines[ln][offset-1] == ',':
            offset -= 1
        self.start = Position(ln, offset)
        if previous:
            previous.end = Position(ln, offset)
        if isinstance(self.value, (ast.Attribute, ast.Num, ast.Str, ast.Name)):
            # This will be replaced by the start point of the next arg except for the last arg.  
            self.end = Position(kw.value.lineno - 1, kw.value.col_offset + len(unparse(self.value)))
        else:
            # If this is the last arg, we don't know how to determine the end.
            self.end = None

    def _step_back(self, ln, offset, lines):
        offset -= 1
        if offset == 0:
            ln -= 1
            offset = len(lines[ln])
        return ln, offset
    
class FieldLocator(ast.NodeVisitor):
    
    def visit_Call(self, node):
        f = node.func
        if hasattr(f, 'id') and f.id == 'Field' or hasattr(f, 'attr') and f.attr == 'Field':
            args = []
            previous = None
            for kw in node.keywords:
                arg = Arg(self._lines, kw, previous)
                args.append(arg)
                previous = arg
            self._found.append((node, args))

                
                
    def search_fields(self, lines, filename):
        self._found = []
        self._lines = lines 
        self.visit(ast.parse(''.join(lines), filename))
        return self._found


def convert(filename):
    lines = open(filename).readlines()
    original_text = ''.join(lines)
    locator = FieldLocator()
    lines_to_delete = []
    for node, args in locator.search_fields(lines, filename):
        #print "*", filename, node.lineno, node.args and unparse(node.args[0]) or '?'
        type_arg = None
        type_args = []
        for arg in reversed(args):
            #print "  -", arg.start, arg.end, unparse(arg.kw)
            if arg.name == 'type' and isinstance(arg.value, (ast.Name, ast.Attribute)):
                type_arg = arg
            elif arg.name in TYPE_KWARGS:
                type_args.insert(0, arg)
                if arg.end is None:
                    # The end of the last argument may not be always obvious!
                    print "Warning: %s line %d: Can't determine end of %s" % \
                        (filename, arg.start.ln+1, unparse(arg.kw))
                else:
                    lines[arg.start.ln] = lines[arg.start.ln][:arg.start.offset] + lines[arg.end.ln][arg.end.offset:]
                    for ln in range(arg.start.ln+1, arg.end.ln+1):
                        lines_to_delete.append(ln)
                    if type_arg and type_arg.end.ln == arg.end.ln:
                        type_arg.end.ln = arg.start.ln
                        type_arg.end.offset -= arg.end.offset - arg.start.offset
        unparsed_type_args = ', '.join([unparse(a.kw) for a in type_args])
        if type_arg:
            ln, offset = type_arg.end.ln, type_arg.end.offset
            assert lines[ln][:offset].endswith(unparse(type_arg.value))
            insert = '('+ unparsed_type_args +')'
        elif type_args:
            ln, offset = type_args[0].start.ln, type_args[0].start.offset
            argnames = [a.name for a in type_args]
            
            if 'maxlen' in argnames:
                type_cls = 'pd.String'
            elif 'precision' in argnames:
                type_cls = 'pd.Float'
            elif 'utc' in argnames:
                type_cls = 'pd.DateTime'
            elif 'format' in argnames:
                fmt = unparse(find('format', type_args, key=lambda a: a.name).value)
                if fmt.startswith('pd.Date.'):
                    type_cls = 'pd.Date'
                elif fmt.startswith('pd.Time.'):
                    type_cls = 'pd.Time'
                elif fmt.startswith('pd.DateTime.'):
                    type_cls = 'pd.DateTime'
                else:
                    type_cls = None
            else:
                type_cls = None
            if type_cls:
                insert = ', type=%s(%s)' % (type_cls, unparsed_type_args)
            elif [name for name in argnames if name not in ('not_null', 'unique')]:
                field_id = node.args and unparse(node.args[0]) or '?'
                print "%s line %d: Can't determine data type of field %s (%s)" % \
                    (filename, node.lineno, field_id, unparsed_type_args)
                sys.exit(1)
                #insert = ', '+ unparsed_type_args
            else:
                insert = ', '+ unparsed_type_args
        else:
            insert = None
        if insert:
            lines[ln] = lines[ln][:offset] + insert + lines[ln][offset:]
        
    for i, ln in enumerate(sorted(lines_to_delete)):
        del lines[ln-i]
    new_text = ''.join(lines)
    if new_text != original_text:
        try:
            ast.parse(new_text)
        except SyntaxError as e:
            print "Invalid syntax after conversion at %s, line %d:" % (filename, e.lineno)
            print ''.join(['%d: %s' % (ln, lines[ln])
                           for ln in range(max(0, e.lineno-6), min(e.lineno+2, len(lines)-1))])
            sys.exit(1)
        else:
            #print ''.join(['%d: %s' % (ln, lines[ln]) for ln in range(len(lines))])
            open(filename, 'w').write(new_text)

def run(filename):
    if os.path.isfile(filename) and filename.endswith('.py'):
        convert(filename)
    elif os.path.isdir(filename):
        for x in os.listdir(filename):
            run(os.path.join(filename, x))

if __name__ == '__main__':
    for filename in sys.argv[1:]:
        run(filename)
        