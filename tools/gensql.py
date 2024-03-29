#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Nástroj pro zpracování specifikací databází
# 
# Copyright (C) 2002-2013 Brailcom, o.p.s.
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
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""Tento program slouží ke zpracování specifikace struktury databáze.

Poskytuje následující funkce:

- Generování SQL příkazů pro inicializaci obsahu databáze.

- Kontrola specifikace proti obsahu databáze a generování SQL příkazů pro
  aktualizaci obsahu databáze.

- Různé konzistenční kontroly.

(Ne všechny tyto funkce jsou v současné době implementovány.)

Pro informaci o použití programu jej spusťte s argumentem '--help'.

Specifikační soubor databáze má podobu pythonového modulu.  Při jeho zpracování
je takový modul načten s namespace tohoto programu, není tedy nutno nic
zvláštního importovat (a je potřeba dávat pozor na konflikty jmen).

Ve specifikaci je možno používat všechny veřejné symboly definované v tomto
programu.  Pomocí specifikačních tříd lze definovat zejména tabulky, views,
sekvence a funkce.  Pro definici těchto objektů se nepoužívají přímo
konstruktory odpovídajících tříd, nýbrž obalující funkce, viz například
'table()', 'view()', 'sequence()', 'function()'.  Pokud pro nějaký objekt
nebo účel není definován příslušný specifikační objekt, lze využít funkce
'sql_raw()' a 'sql_raw_input()', umožňující zadat přímo SQL příkazy.  Na
objekty zadané přímo prostřednictvím SQL příkazů nejsou aplikovány žádné
kontroly.

"""

import copy
import functools
import getopt
import inspect
import operator
import re
import string
import sys
import UserDict
import types

from pytis.util import *
import pytis.data

imp.reload(sys)
sys.setdefaultencoding('utf-8')

gensql_file = 'gensql'
_CONV_PREPROCESSED_NAMES = ('_log_update_trigger', '_inserts', '_updates', '_deletes', 'log_trigger',)


exit_code = 0
_EXIT_USAGE = 1
_EXIT_NOT_IMPLEMENTED = 2
_EXIT_ERROR = 3

def _signal_error(message):
    sys.stderr.write(message)
    global exit_code
    exit_code = _EXIT_ERROR

class GensqlError(Exception):
    """Výjimka signalizovaná tímto programem při chybách specifikace."""
    

def _gsql_escape(s):
    return s.replace("'", "\\'")


def _gsql_column_table_column(column):
    if is_sequence(column):
        column = find(1, column,
                      test=(lambda x, y: x is not None and y is not None))
    pos = column.rfind('.')
    if pos == -1:
        result = None, column
    else:
        result = column[:pos], column[pos+1:]
    return result


def _gsql_format_type(type_):
    if type(type_) == type(''):
        result = type_
    elif type_.__class__ == pytis.data.String:
        minlen = type_.minlen()
        maxlen = type_.maxlen()
        if maxlen is None:
            result = 'text'
        elif maxlen == minlen:
            result = 'char(%d)' % maxlen
        else:
            result = 'varchar(%d)' % maxlen
    elif type_.__class__  == pytis.data.DateTime:
        if type_.utc():
            result = 'timestamp(0)'
        else:
            result = 'timestamp (0) with time zone'
    else:
        MAPPING = {pytis.data.Integer:   'int',
                   pytis.data.Serial:    'serial',
                   pytis.data.Oid:       'oid',
                   pytis.data.Float:     'numeric',
                   pytis.data.Boolean:   'bool',
                   pytis.data.Date:      'date',
                   pytis.data.Time:      'time',
                   pytis.data.Binary:    'bytea',
                   pytis.data.Image:     'bytea',
                   pytis.data.Color:     'varchar(7)',
                   pytis.data.LTree:    'ltree',
                   }
        try:
            result = MAPPING[type_.__class__]
        except KeyError:
            raise ProgramError('Unknown type', type_)
    return result
        
def _gsql_warning(message):
    if _GsqlConfig.warnings:
        return '-- WARNING: %s\n' % message
    else:
        return ''


_convert_local_names = []

class _GsqlSpec(object):

    _SQL_NAME = ''
    _PGSQL_TYPE = ''
    
    _counter = Counter()
    _groups = None
    _group_list = []
    _seen_names = []
    
    def __init__(self, name, depends=(), doc=None, grant=(), convert=True, schemas=None):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno objektu, string nebo 'None' (v kterémžto případě je
            jméno vygenerováno)
          depends -- sekvence instancí '_GsqlSpec' nebo jejich jmen (strings),
            na kterých definice objektu závisí.  Všechny tyto objekty musí být
            v databázi vytvořeny dříve než tento objekt.  Řada závislostí může
            být rozpoznávána automaticky, některé však nikoliv, zejména ty,
            které vyplývají z nahrubo zadaných SQL příkazů, a ty je pak nutno
            uvést explicitně v tomto argumentu.  Druhotným kritériem řazení
            objektů je vedle závislostí jejich sériové číslo.
          doc -- dokumentace objektu, string nebo 'None' (žádná dokumentace)
          grant -- specifikace přístupových práv objektu pro příkaz GRANT;
            sekvence dvouprvkových sekvencí tvaru (SPEC, GROUP), kde SPEC je
            string SQL specifikace druhu přístupu (například 'INSERT' nebo
            'ALL') a GROUP je SQL string určující odpovídající skupinu
            uživatelů

        """
        self._serial_number = self._counter.next()
        if name is None:
            name = '@%d' % self._serial_number
        self._set_name(name)
        self._depends = depends
        self._conversion_depends = tuple([d for d in depends if d != 'cms_users_table'])
        self._doc = doc
        self._grant = grant
        for g in grant:
            group = g[1]
            if group not in _GsqlSpec._group_list:
                _GsqlSpec._group_list.append(group)
        self._schemas = schemas
        self._convert = convert
        self._gensql_file = gensql_file

    def _set_name(self, name):
        if name in self._seen_names:
            raise ProgramError("Duplicate object name", name)
        self._name = name
        self._seen_names.append(name)
        
    def _set_schemas(self, schemas):
        if schemas is not None:
            assert isinstance(schemas, (tuple, list,)), ('invalid schema list', schemas,)
            if __debug__:
                for s in schemas:
                    assert isinstance(s, basestring), ('invalid schema', s,)
            self._schemas = schemas

    def _grant_command(self, gspec):
        right, group = gspec
        return 'GRANT %s ON %s TO GROUP %s;\n' % (right, self.name(), group)

    def _revoke_command(self):
        groups = _GsqlSpec._groups
        if groups is None:
            groups = ', '.join(map(lambda x: "GROUP %s" % x, _GsqlSpec._group_list))
            if groups:
                groups = ', %s' % groups
            _GsqlSpec._groups = groups
        return 'REVOKE ALL ON %s FROM PUBLIC%s;\n' % (self.name(), groups)

    def name(self):
        """Vrať jméno objektu zadané v konstruktoru."""
        return self._name

    def extra_names(self):
        """Return sequence of additional associated object names.
        
        For instance, index names or names of sequences corresponding to serial
        columns may be returned.
        """
        return ()

    def depends(self):
        """Vrať tuple objektů, na kterých tento objekt závisí.

        Závislostní tuple je zkonstruováno z argumentu konstruktoru 'depends'.

        """
        return self._depends

    def serial_number(self):
        """Vrať pořadové číslo objektu.

        Pořadová čísla jsou objektům přiřazována postupně dle pořadí jejich
        definic.

        """
        return self._serial_number

    def output(self, *args, **kwargs):
        """Vrať string obsahující SQL příkazy nutné k vygenerování objektu.

        V této třídě metoda vyvolává výjimku 'ProgramError'.

        """
        output = self._output(*args, **kwargs)
        if self._schemas is None:
            result = output
        else:
            result = ''
            for s in self._schemas:
                result += self._search_path_command(s)
                result += output
            result += 'SET search_path TO "$user",public;\n'
        return result

    def _output(self):
        raise ProgramError('Not implemented')

    def _search_path_command(self, search_path):
        return "SET search_path TO %s;\n" % (search_path,)

    def outputall(self):
        """Vrať string obsahující SQL příkazy nutné k vygenerování objektu
        včetně dat.


        """
        return self.output()

    def reoutput(self):
        """Vrať string obsahující SQL příkazy pro redefinici objektu.

        Pro třídy, pro které redefinice objektu nemá smysl, vrací prázdný
        řetězec.

        """
        return ''

    def db_all_names(class_, connection):
        """Vrať sekvenci jmen všech objektů v databázi daného typu.

        Argumenty:

          connection -- PgConnection objekt zpřístupňující příslušnou databázi
          
        """
        data = connection.query(("select relname from pg_class, pg_namespace "+
                                 "where relkind='%s' and "+
                                 "pg_class.relnamespace=pg_namespace.oid and "+
                                 "pg_namespace.nspname='public'") %
                                class_._PGSQL_TYPE)
        names = []
        for i in range(data.ntuples):
            names.append(data.getvalue(i, 0))
        return names
    db_all_names = classmethod(db_all_names)

    def db_update(self, connection):
        """Vrať SQL příkazy potřebné k updatu databáze dle aktuální definice.

        Metoda předpokládá, že objekt odpovídajícího jména a typu v databázi
        existuje.

        Argumenty:
        
          connection -- PgConnection objekt zpřístupňující příslušnou databázi

        """
        return '-- %s up to date\n' % self.name()

    def db_remove(class_, name):
        """Vrať SQL příkazy (string) potřebné k odstranění objektu z databáze.

        Argumenty:

          name -- jméno objektu, který má být odstraněn; string
          
        """
        class_sql_name = class_._SQL_NAME
        if class_sql_name:
            result = "DROP %s %s;\n" % (class_sql_name, name,)
        else:
            result = "-- DROP ??? %s;\n" % (name,)
        return result
    db_remove = classmethod(db_remove)

    def _convert_indent(self, text, level):
        if text is None:
            return None
        lines = text.split('\n')
        lines = [' '*level + l for l in lines]
        return string.join(lines, '\n')

    def _convert_name(self, name=None, new=False, short=False):
        if name is None:
            name = self._name
        components = [(c.capitalize() if c else 'X') for c in name.split('_')]
        converted = string.join(components, '').replace('í', 'ii').replace('@', 'X')
        if new:
            _convert_local_names.append(converted)
        elif not short and converted not in _convert_local_names:
            converted = 'db.' + converted
        return converted

    def _convert_id_name(self, name):
        converted = name.replace('(', '__').replace(')', '__').replace(', ', '__')
        pos = converted.find(' ')
        if pos >= 0:
            converted = converted[:pos]
        return converted

    def _convert_doc(self):
        doc = self._doc
        if not doc:
            return None
        doc = doc.replace('\\', '\\\\')
        doc = doc.replace('"', '\\"')
        doc = string.join([line.strip() for line in doc.split('\n')], '\n')
        return '"""%s"""' % (doc,)

    def _convert_literal(self, literal):
        return literal.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')

    def _convert_value(self, value, ctype=None):
        if isinstance(value, int):
            return str(value)
        elif value.lower() == 'null':
            return 'None'
        elif value.lower() in ("'f'", 'false',) and isinstance(ctype, pytis.data.Boolean):
            return 'False'
        elif value.lower() in ("'t'", 'true',) and isinstance(ctype, pytis.data.Boolean):
            return 'True'
        elif value[0] == "'" and value[-1] == "'" and value[1:-1].find("'") == -1:
            return value.replace('\n', '\\n')
        else:
            try:
                float(value)
                return value
            except:
                return "sqlalchemy.text('%s')" % (value.replace('\\', '\\\\').replace("'", "\\'"),)

    def _convert_string_type(self, stype, allow_none=False, constraints=()):
        mapping = {'name': 'pytis.data.Name()',
                   'smallint': 'pytis.data.SmallInteger()',
                   'integer': 'pytis.data.Integer()',
                   'int': 'pytis.data.Integer()',
                   'bigint': 'pytis.data.LargeInteger()',
                   'bigserial': 'pytis.data.LargeSerial()',
                   'bytea': 'pytis.data.Binary()',
                   'inet': 'pytis.data.Inet()',
                   'date': 'pytis.data.Date()',
                   'time': 'pytis.data.Time()',
                   'timestamp': 'pytis.data.DateTime()', # assumes UTC, not always valid
                   'timestamp(0)': 'pytis.data.DateTime()', # assumes UTC, not always valid
                   'timestamp(0) without time zone': 'pytis.data.DateTime()',
                   'timestamp with time zone': 'pytis.data.DateTime(utc=False)',
                   'macaddr': 'pytis.data.Macaddr()',
                   'ltree': 'pytis.data.LTree()',
                   'boolean': 'pytis.data.Boolean()',
                   'bool': 'pytis.data.Boolean()',
                   'text': 'pytis.data.String()',
                   'void': 'None',
                   'trigger': 'sql.G_CONVERT_THIS_FUNCTION_TO_TRIGGER',
                   'record': 'sql.SQLFunctional.RECORD',
                   'float(40)': 'pytis.data.DoublePrecision()',
                   }
        type_ = mapping.get(stype.lower())
        if type_ is None:
            match = re.match('^(?P<var>var)?char\((?P<len>[0-9]+)\)$', stype, re.I)
            if match:
                groups = match.groupdict()
                minlen = '' if groups['var'] else 'minlen=%s, ' % (groups['len'],)
                type_ = 'pytis.data.String(%smaxlen=%s)' % (minlen, groups['len'],)
            else:
                match = re.match('(numeric|decimal)\(([0-9]+), *([0-9]+)\)', stype)
                if match:
                    type_ = 'pytis.data.Float(digits=%s, precision=%s)' % match.groups()[1:]
                else:
                    match = re.match('(numeric|decimal)\(([0-9]+)\)', stype)
                    if match:
                        type_ = 'pytis.data.Float(digits=%s)' % match.groups()[1:]
                    elif allow_none:
                        type_ = None
                    else:
                        type_ = 'XXX: %s' % (stype,)
        if 'not null' in constraints or 'unique not null' in constraints and type_ and type_[-1] == ')':
            if type_[-2] != '(':
                type_ = type_[:-1] + ', )'
            type_ = type_[:-1] + 'not_null=True)'
        return type_

    def _convert_pytis_type(self, ctype, constraints=()):
        arguments = []
        if isinstance(ctype, pytis.data.String):
            if ctype.minlen() is not None:
                arguments.append('minlen=%s' % (ctype.minlen(),))
            if ctype.maxlen() is not None:
                arguments.append('maxlen=%s' % (ctype.maxlen(),))
        elif isinstance(ctype, pytis.data.Float):
            if ctype.precision() is not None:
                arguments.append('precision=%s' % (ctype.precision(),))
            if ctype.digits() is not None:
                arguments.append('digits=%s' % (ctype.digits(),))
        elif isinstance(ctype, (pytis.data.DateTime, pytis.data.Time,)) and not isinstance(ctype, pytis.data.Date):
            if not ctype.utc():
                arguments.append('utc=False')
        if (ctype.not_null() and not isinstance(ctype, pytis.data.Boolean)) or 'not null' in constraints or 'unique not null' in constraints:
            if not isinstance(ctype, pytis.data.Serial):
                arguments.append('not_null=True')
        else:
            arguments.append('not_null=False')
        return 'pytis.data.%s(%s)' % (ctype.__class__.__name__, string.join(arguments, ', '),)
        
    def _convert_column(self, column):
        name = column.name
        if name[0] == '"':
            name = name.strip('"')
        else:
            name = name.lower()
        pos = name.rfind('.')
        if pos >= 0:
            name = name[pos+1:]
        cls = 'sql.PrimaryColumn' if name in [c.split('.')[-1].lower() for c in self.key_columns()] else 'sql.Column'
        name = repr(name)
        constraints = [c.lower() for c in column.constraints]
        ctype = column.type
        if isinstance(ctype, pytis.data.Type):
            type_ = self._convert_pytis_type(ctype, constraints)
        else:
            type_ = self._convert_string_type(column.type, constraints=constraints)
        unique = 'unique' in constraints or 'unique not null' in constraints
        if column.default is None:
            default = None
        else:
            if isinstance(column.default, tuple):
                if len(column.default) == 1:
                    default = self._convert_value(column.default[0], ctype)
                else:
                    default = 'XXX:default:%s' % (column.default,)
            else:
                default = self._convert_value(column.default, ctype)
        c_references = column.references
        if c_references:
            if isinstance(c_references, tuple):
                if len(c_references) == 1:
                    c_references = c_references[0]
                else:
                    c_references = None
            if c_references:
                components = re.split('[ \n]+', c_references, flags=re.M)
                referenced_table = components.pop(0)
                if referenced_table == 'cms_users_table':
                    referenced_table = 'db.cms_users_table.value(globals())'
                else:
                    referenced_table = repr(referenced_table)
                references = "sql.gA(%s" % (referenced_table,)
                initially = ''
                while components:
                    keyword = components.pop(0).lower()
                    if keyword == 'on':
                        action = (components and components.pop(0).lower())
                        if (components and action in ('update', 'delete',) and
                            components[0].lower() in ('cascade', 'delete', 'restrict',)):
                            reaction = components.pop(0).upper()
                            if references and components == ['INITIALLY', 'DEFERRED']:
                                initially = 'DEFERRED'
                                components = []
                            references += ", on%s='%s'" % (action, reaction,)
                        elif (len(components) >= 2 and action in ('update', 'delete',) and
                            (components[0].lower(), components[1].lower(),) == ('set', 'null',)):
                            references += ", on%s='SET NULL'" % (action,)
                            components = components[2:]
                        else:
                            references = None
                            break
                    elif keyword == 'initially' and components.pop(0).lower() == 'deferred' and not components:
                        references += ", onupdate='NO ACTION', ondelete='NO ACTION'"
                        initially = 'DEFERRED'
                    else:
                        references = None
                        break
                if initially:
                    references += ", initially='%s'" % (initially,)
            else:
                references = None
            if references is None:
                references = 'None #XXX: %s' % (column.references,)
            else:
                references += ')'
        else:
            references = None
        spec = ('%s(%s, %s' % (cls, name, type_,))
        if column.doc:
            spec += ', doc="%s"' % (column.doc.replace('\n', '\\n').replace('"', '\\"'),)
        if unique:
            spec += ', unique=%s' % (repr(unique),)
        if default is not None:
            spec += ', default=%s' % (default,)
        if references is not None:
            spec += ', references=%s' % (references,)
        if column.index:
            index = str(column.index)
        else:
            index = None
        if index:
            spec += ', index=%s' % (index,)
        for c in column.constraints:
            if c.lower().startswith('check(') or c.lower().startswith('check ('):
                c = c[5:].strip()
                spec += ', check="%s"' % (c[1:-1],)
        for c in constraints:
            if c not in ('unique', 'not null',) and not c.startswith('check(') and not c.startswith('check ('):
                spec = spec + (', #XXX:%s' % (c,))
        spec += ')'
        return spec

    def _convert_schemas(self, items):
        schemas = None
        if _GsqlConfig.application == 'pytis':
            if (self._name.startswith('cms_') or
                (isinstance(self, _GsqlRaw) and
                 (self._sql.startswith('create or replace rule session_delete as on delete to cms_session') or
                  self._sql.startswith('CREATE UNIQUE INDEX cms_menu_structure_unique_tree_order')))):
                schemas = 'db.cms_schemas.value(globals())'
            elif self._schemas == ('xxx',):
                schemas = 'db.pytis_schemas.value(globals())'                
        elif self._schemas:
            for name, s_tuple in _GsqlConfig.convert_schemas:
                if s_tuple == self._schemas:
                    if self._name in _CONV_PREPROCESSED_NAMES:
                        schemas = '%s' % (name,)
                    else:
                        schemas = 'db.%s' % (name,)
                    break
            if schemas is None:
                schemas = repr(tuple([tuple([s.strip() for s in ss.split(',')]) for ss in self._schemas]))
        if schemas is not None:
            items.append('    schemas = %s' % (schemas,))

    def _convert_depends(self):
        def convert(dependency):
            dependency = dependency.lower()
            if dependency.find('.') >= 0:
                return "sql.object_by_name('%s')" % (dependency,)
            else:
                return self._convert_name(dependency)
        depends_string = string.join([convert(d) for d in self._conversion_depends], ', ')
        if depends_string:
            depends_string += ','
        return '    depends_on = (%s)' % (depends_string,)

    def _convert_add_raw_dependencies(self, raw):
        if raw.find('pracovnik()') >= 0:
            self._add_conversion_dependency('pracovnik', None)
        while True:
            match = re.search(' (from|join|on) ([a-zA-Z0-9][a-zA-Z_0-9]+)($|[ ,;(])', raw, flags=re.I|re.M)
            if not match:
                break
            raw = raw[match.end():].lstrip()
            identifier = match.group(2)
            if identifier.endswith('_seq'):
                identifier = string.join(string.split('_')[:-2], '_')
            ignored_objects = ('profiles', 'kurzy_cnb', 'new', 'public', 'abra_mirror', 'generate_series',
                               'dblink', 'date_trunc', 'diff', 'avg', 'case', 'current_date',
                               'insert', 'update', 'delete', 'view', 'function', 'table', 'regexp_matches',
                               'bv_users_cfg', 'solv_users_cfg', 'dat_vypisu', 'nulovy_cenik',
                               'relnamespace', 'regexp_split_to_table',)
            if (len(identifier) < 3 or
                identifier.lower() in ignored_objects or
                identifier.startswith('temp_') or
                identifier.find('sogo') >= 0):
                continue
            self._add_conversion_dependency(identifier, None)
        
    def _convert_grant(self):
        if self._grant == (('all', _GsqlConfig.application,),):
            if self._name in _CONV_PREPROCESSED_NAMES:
                grant = 'default_access_rights.value(globals())'
            else:
                grant = 'db.default_access_rights.value(globals())'
        elif self._grant == (('all', 'cms',),):
            grant = 'db.cms_rights.value(globals())'
        elif self._grant == (('all', 'cmsrw',),):
            grant = 'db.cms_rights_rw.value(globals())'
        elif self._grant == (('insert', 'pytis'), ('delete', 'pytis'), ('select', 'pytiswebuser')):
            grant = 'db.http_attachment_storage_rights.value(globals())'
        else:
            grant = repr(self._grant).replace('"', '')
        return '    access_rights = %s' % (grant,)
    
    def _convert_local_name(self, name):
        if name in ('a', 'c', 'r', 't',):
            name = name + '_'
        return name
               
    def convert(self):
        "Vrať novou pythonovou specifikaci daného objektu jako string."
        return '#XXX:%s' % (self,)

    def _add_conversion_dependency(self, o, schema):
        if isinstance(o, basestring):
            pos = o.find('(')
            if pos >= 0:
                o = o[:pos].rstrip()
            if o.startswith('pg_') or o.startswith('t_pytis_passwords'):
                return
        if o not in self._depends and o is not self and o != self._name:
            self._depends = self._depends + (o,)
        if schema is not None:
            self._conversion_depends = tuple([d for d in self._conversion_depends if d != o])
            o = '%s.%s' % (schema, o,)
        if o not in self._conversion_depends and o is not self and o != self._name:
            self._conversion_depends = self._conversion_depends + (o,)            


class Column(object):
    """Úložná třída specifikace sloupce."""
    
    def __init__(self, name, type, constraints=(), references=None,
                 default=None, index=None, doc=None):
        """Nastav atributy.

        Argumenty:

          name -- jméno sloupce, SQL string
          type -- typ sloupce, buď instance třídy 'pytis.data.Type', nebo SQL
            string
          constraints -- sekvence omezení na sloupec, SQL strings; zde se
            neuvádí 'PRIMARY KEY', definice sloupce primárního klíče se
            provádí třídou 'PrimaryColumn'
          references -- odkazovaná tabulka sloupce (\"REFERENCES\"), SQL
            strings
          default -- implicitní hodnota sloupce, SQL string
          index -- if 'True', create index for this column; if a dictionary
            then it defines additional index options, currently only
            'method=METHOD' is supported where METHOD is the index method
          doc -- dokumentace sloupce, string nebo 'None' (žádná dokumentace)

        """
        self.name = name
        self.type = type
        self.constraints = constraints
        self.references = references
        self.default = default
        self.index = index
        self.doc = doc

class PrimaryColumn(Column):
    """Úložná třída specifikace sloupce, který je primárním klíčem.

    Stejné jako 'Column', avšak slouží exkluzivně pro definici sloupců, které
    jsou primárními klíči.

    """

class ViewColumn(object):
    """Úložná třída specifikace sloupce view."""

    def __init__(self, name, alias=None, sql=None, type=None,
                 insert='', update=''):
        """Nastav atributy.

        Argumenty:

          name -- jméno sloupce, SQL string ve tvaru 'TABULKA.SLOUPEC'.  Ve
            view neasociovaných s konkrétní jedinou tabulkou může být též
            sekvence jmen sloupců, potom bude odpovídající view sjednocením
            více tabulek prostřednictvím operátoru UNION a v 'name' nezmíněné
            tabulky budou na místě tohoto sloupce generovat NULL.
          alias -- přezdívka sloupce (\"AS\"), SQL string nebo 'None'; je-li
            'None', bude nastaveno na hodnotu 'name'.
          sql -- obecný SQL string umožňující specifikaci view sloupce jako SQL
            výrazu; je-li specifikován, musí být také specifikován alias a name
            musí být None.
          type -- explicitně určený typ -- hlavní využití je pro UNIONY, kde se
            vyskytují NULL hodnoty.  
          insert -- řetězec, který se použije pro vložení hodnoty do sloupce
            tabulky pro defaultně generovaný insert rule. Je-li '', použije se
            standardní new hodnota, je-li None, nebude se sloupec v insert rulu
            vyskytovat.
          update -- řetězec, který se použije pro aktualizaci hodnoty sloupce
            tabulky pro defaultně generovaný update rule. Je-li '', použije se
            standardní new hodnota, je-li None, nebude se sloupec v update rulu
            vyskytovat.

        """
        assert (is_sequence(name) and not sql) or \
               (is_sequence(sql) and alias and not name) or \
               (name and not sql) or \
               (sql and alias and not name)
        if not name:
            self.name = alias
            self.insert = None
            self.update = None
        else:    
            self.name = name
            self.insert = insert
            self.update = update
        if name and not alias:
            alias = _gsql_column_table_column(name)[1]
        self.alias = alias
        self.sql = sql
        self.type = type
        if self.insert == '':
            self.insert = 'new.%s' % (alias)
        if self.update == '':
            self.update = 'new.%s' % (alias)


class JoinType(object):
    """Specifikační třída pro typy joinů."""
    FROM = 'FROM'
    INNER = 'INNER'
    LEFT_OUTER = 'LEFT_OUTER'
    RIGHT_OUTER = 'RIGHT_OUTER'
    FULL_OUTER = 'FULL_OUTER'
    CROSS = 'CROSS'
    TEMPLATES = {FROM: 'FROM %s %s%s',
                 INNER: 'INNER JOIN %s %s\n ON (%s)',                       
                 LEFT_OUTER: 'LEFT OUTER JOIN %s %s\n ON (%s)',
                 RIGHT_OUTER: 'RIGHT OUTER JOIN %s %s\n ON (%s)',
                 FULL_OUTER: 'FULL OUTER JOIN %s %s\n ON (%s)',
                 CROSS: 'CROSS JOIN %s %s%s',
                 }
    
class SelectRelation(object):
    """Úložná třída specifikace relace pro select."""
    def __init__(self, relation, alias=None,
                 key_column=None, exclude_columns=(), column_aliases=(),
                 jointype=JoinType.FROM, condition=None,
                 insert_columns=(), update_columns=(),
                 schema=None
                 ):
        """Specifikace relace pro SQL select.
        Argumenty:

          relation -- název tabulky nebo view, příp. instance Select pro
            použití jako subselect ve ViewNG.
          alias -- alias pro použití při výběru sloupců.
          key_column -- název sloupce, který je pro danou relaci klíčem.
          exclude_columns -- seznam názvů sloupců, které nemají být do view
            zahrnuty. Je-li None, budou použity všechny sloupce ze všech
            relací (pozor na konflikty jmen!). Pokud je v seznamu
            znak '*', týká se specifikace všech sloupců dané relace.
          column_aliases -- seznam dvojic (column, alias) uvádějící
            alias pro uvedený sloupec.
          jointype -- typ joinu.
          condition -- podmínka, která se použije ve specifikaci ON
            nebo v případě typu FROM jako WHERE.
          schema -- není-li 'None', jde o řetězec určující schéma, které se má
            použít pro tuto relaci
        """
        assert jointype != JoinType.CROSS or \
               condition is None
        assert isinstance(relation, basestring) or \
               isinstance(relation, Select)
        assert schema is None or isinstance(schema, basestring), schema
        self.relation = relation
        self.schema = schema
        self.alias = alias
        self.key_column = key_column
        self.exclude_columns = exclude_columns
        self.column_aliases = column_aliases
        self.jointype = jointype
        self.condition = condition
        self.insert_columns = insert_columns
        self.update_columns = update_columns


class SelectSetType(object):
    """Specifikační třída pro typy kombinace selectů."""
    UNION = 'UNION'
    INTERSECT = 'INTERSECT'
    EXCEPT = 'EXCEPT'
    UNION_ALL = 'UNION_ALL'
    INTERSECT_ALL = 'INTERSECT_ALL'
    EXCEPT_ALL = 'EXCEPT_ALL'

class SelectSet(object):
    """Úložná třída specifikace kombinace selectů."""
    _FORMAT_SET = {
        SelectSetType.UNION: 'UNION',
        SelectSetType.INTERSECT: 'INTERSECT',
        SelectSetType.EXCEPT: 'EXCEPT',
        SelectSetType.UNION_ALL: 'UNION ALL',
        SelectSetType.INTERSECT_ALL: 'INTERSECT ALL',
        SelectSetType.EXCEPT_ALL: 'EXCEPT ALL',
        }
    def __init__(self, select, 
                 settype=None
                 ):
        """Úložná třída specifikace kombinace selectů.
        Argumenty:

          select -- název pojmenovaného selectu nebo instance
            Select.
          settype -- typ spojení selectů - konstanta třídy SelectSetType. 
        """
        self.select = select
        self.settype = settype    

    def format_select(self, indent=0):
        output = self.select.format_select(indent=indent)        
        if self.settype:
            outputset = ' ' * (indent+1) + self._FORMAT_SET[self.settype]
            output = '%s\n%s' % (outputset, output)
        return output

    def sort_columns(self, aliases):
        self.select.sort_columns(aliases)

class TableView(object):
    """Úložná třída specifikace view asociovaného s tabulkou.

    Tato třída se využívá pouze ve specifikaci třídy '_GsqlTable'.

    """

    def __init__(self, columns, exclude=None, name=None, **kwargs):
        """Nastav atributy.

        Argumenty:
        
          columns -- stejné jako v '_GsqlView.__init__()', vždy jsou
            automaticky přidány všechny definované sloupce tabulky neuvedené
            v argumentu 'exclude'
          exclude -- sekvence jmen sloupců (SQL strings) dané tabulky, které
            nemají být do view zahrnuty; smí být též 'None', v kterémžto
            případě je ekvivalentní prázdné sekvenci
          name -- jméno view; smí být též 'None', v kterémžto případě je jméno
            odvozeno ze jména tabulky
          kwargs -- klíčové argumenty předané konstruktoru třídy '_GsqlView';
            smí se jednat pouze o volitelné argumenty onoho konstruktoru,
            povinné argumenty jsou doplněny ve třídě '_GsqlTable' automaticky

        """
        assert is_sequence(columns)
        assert exclude is None or is_sequence(exclude)
        self.columns = columns
        self.exclude = exclude or ()
        self.name = name
        self.kwargs = kwargs


class _GsqlType(_GsqlSpec):
    """Specifikace SQL typu."""

    _SQL_NAME = 'TYPE'
    _PGSQL_TYPE = 'c'
    
    def __init__(self, name, columns, **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- název typu
          columns -- specifikace sloupců a jejich typů, sekvence instancí
            třídy Column
        """    
        super(_GsqlType, self).__init__(name, **kwargs)
        self._columns = columns
        
    def _column_column(self, column):        
        return _gsql_column_table_column(column.name)[1]

    def _format_column(self, column):
        result = '%s %s' % (self._column_column(column),
                            _gsql_format_type(column.type))
        return result

    def _output(self):
        columns = [self._format_column(c) for c in self._columns]
        columns = string.join(columns, ',\n        ')
        result = ('CREATE TYPE %s AS (\n%s);\n' %
                  (self._name, columns))
        return result

    def _convert_column(self, column):
        name = column.name.lower()
        ctype = column.type
        if isinstance(ctype, pytis.data.Type):
            type_ = self._convert_pytis_type(ctype)
        elif isinstance(ctype, basestring):
            type_ = self._convert_string_type(ctype)
        else:
            type_ = '#XXX:ttype:%s' % (ctype,)
        return 'sql.Column(%s, %s)' % (repr(name), type_,)

    def convert(self):
        items = ['class %s(sql.SQLType):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name.lower()),))
        self._convert_schemas(items)
        items.append('    fields = (')
        for c in self._columns:
            items.append('              %s,' % (self._convert_column(c),))
        items.append('             )')
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        result = string.join(items, '\n') + '\n'
        return result        


class ArgumentType(object):
    """Úložná třída specifikace typu argumentu pro funkce.

    Tato třída se využívá pouze ve specifikaci třídy '_GsqlFunction'.
    """
    def __init__(self, typ, name='', out=False):
        """Nastav atributy.

        Argumenty:
        
          typ -- název typu, instance pytis.data.Type nebo _GsqlType.
          name -- volitelné jméno argumentu
          out -- je-li True, jde o výstupní argument
        """
        self.typ = typ
        self.name = name
        self.out = out

class ReturnType(object):
    """Úložná třída specifikace návratového typu.

    Tato třída se využívá pouze ve specifikaci třídy '_GsqlFunction'.

    """
    def __init__(self, name, setof=False):
        """Nastav atributy.

        Argumenty:
        
          name -- název typu, instance pytis.data.Type nebo _GsqlType.
          setof -- je-li True, jde o návratový typ SETOF
        """
        self.name = name
        self.setof = setof

class _GsqlSchema(_GsqlSpec):
    """Specifikace SQL schématu."""
    
    _SQL_NAME = 'SCHEMA'
    
    def __init__(self, name, owner=None, **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno schématu, SQL string
          owner -- volitelný řetězec udávající vlastníka schématu.
            Pozor, uvede-li se, pak musí být vytváření provedeno superuserem.
        """
        super(_GsqlSchema, self).__init__(name, **kwargs)
        self._owner = owner
        
    def _output(self):
        if self._owner is not None:
            owner = " AUTHORIZATION %s" % self._owner
        else:
            owner = ''
        result = 'CREATE SCHEMA %s%s;\n' % (self._name, owner)
        return result

    def convert(self):
        items = ['class %s(sql.SQLSchema):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name.lower()),))
        if self._owner:
            items.append('    owner = %s' % (repr(self._owner),))
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        result = string.join(items, '\n') + '\n'
        return result        
        
class _GsqlTable(_GsqlSpec):
    """Specifikace SQL tabulky."""
    
    _SQL_NAME = 'TABLE'
    _PGSQL_TYPE = 'r'
    
    def __init__(self, name, columns, inherits=None, view=None,
                 with_oids=True, sql=None, schemas=None,
                 on_insert=None, on_update=None, on_delete=None,
                 init_values=(), init_columns=(),
                 tablespace=None, upd_log_trigger=None,
                 indexes=(), key_columns=(), **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno tabulky, SQL string
          columns -- specifikace sloupců tabulky, sekvence instancí třídy
            'Column'
          inherits -- sekvence jmen poděděných tabulek (SQL strings) nebo
            'None' (nedědí se žádná tabulka)
          sql -- SQL string SQL definic přidaný za definici sloupců, lze jej
            využít pro doplnění SQL konstrukcí souvisejících se sloupci, které
            nelze zadat jiným způsobem
          schemas -- není-li 'None', definuje schémata, ve kterých má být
            tabulka vytvořena, jde o sekvenci řetězců obsahujících textové
            definice postgresové search_path určující search_path nastavenou
            při vytváření tabulky, tabulka je samostatně vytvořena pro každý
            z prvků této sekvence
          on_insert -- doplňující akce, které mají být provedeny při vložení
            záznamu do tabulky, SQL string
          on_update -- doplňující akce, které mají být provedeny při updatu
            záznamu tabulky, SQL string
          on_delete -- doplňující akce, které mají být provedeny při smazání
            záznamu z tabulky, SQL string
          view -- specifikace view asociovaného s tabulkou, instance třídy
            'TableView'.  Takové view může obsahovat pouze sloupce z této
            tabulky a také přebírá následující její vlastnosti (nejsou-li
            v definici view uvedeny explicitně): klíčové sloupce, dokumentaci,
            specifikaci přístupových práv.  Smí být též sekvence instancí třídy
            'TableView', pak je definován odpovídající počet views.
            Vícetabulková view, je nutno specifikovat pomocí třídy
            '_GsqlView'.
          init_values -- sekvence iniciálních hodnot vložených do
            tabulky. každý prvek je sekvence SQL strings odpovídající sloupcům
            z argumentu 'init_columns' nebo všem sloupcům tabulky v daném
            pořadí
          init_columns -- sekvence jmen sloupců nebo instancí třídy 'Column',
            pro něž jsou definovány 'init_values'; je-li prázdnou sekvencí,
            jsou to všechny sloupce tabulky
          key_columns -- sequence of column names or instances of 'Column',
            which builds the primary key for the table; it is expected to define
            this argument only if there are no instances of PrimaryColumn in the
            argument columns, which is mostly the case when primary key is defined
            in inherited tables; 
          tablespace -- název tablespace, ve kterém bude tabulka vytvořena  
          upd_log_trigger -- název trigger funkce, která bude logovat změny v
            záznamech, nebo None, pokud se nemá logovat.
          indexes -- sequence of multicolumn index definitions; each element of
            the sequence is a tuple of the form (COLUMNS, OPTIONS), where
            COLUMNS is sequence of column names and OPTIONS is (possibly empty)
            dictionary of index options.  Currently the only supported index
            option is 'method=METHOD' where 'METHOD' is a string defining the
            index method.
          kwargs -- argumenty předané konstruktoru předka

        """
        super(_GsqlTable, self).__init__(name, **kwargs)
        self._columns = columns
        self._inherits = inherits or ()
        self._set_schemas(schemas)
        self._views = map(self._make_view, xtuple(view or ()))
        self._with_oids = with_oids
        self._sql = sql
        self._on_insert, self._on_update, self._on_delete = \
          on_insert, on_update, on_delete
        self._init_values = init_values
        self._tablespace = tablespace
        self._upd_log_trigger = upd_log_trigger
        if not init_columns:
            init_columns = columns
        self._init_columns = [isinstance(c, basestring) and c
                              or self._column_column(c)
                              for c in init_columns]
        self._key_columns = key_columns
        self._indexes = indexes

    def _full_column_name(self, column):
        if not _gsql_column_table_column(column.name)[0]:
            column.name = "%s.%s" % (self._name, column.name)
        return column    

    def _column_column(self, column):        
        return _gsql_column_table_column(column.name)[1]

    def _grant_command(self, gspec, name=None):
        if not name:
            name = self.name()
        right, group = gspec
        return 'GRANT %s ON %s TO GROUP %s;\n' % (right, name, group)

    def _make_view(self, view):
        if view is not None:
            vcolumns = list(view.columns)
            for c in self._columns:                
                if _gsql_column_table_column(c.name)[0] is None:
                    c.name = "%s.%s" % (self._name, c.name)
                if find(c.name, vcolumns, key=lambda c: c.name) is None:
                    vcolumns.append(ViewColumn(c.name))
            kwargs = view.kwargs
            if 'key_columns' not in kwargs:
                kwargs['key_columns'] = None
            vcolumns = map(self._full_column_name, vcolumns)
            vcolumns = filter(lambda x: self._column_column(x) not in
                              view.exclude, vcolumns)
            # Remove also columns specified like table.name
            vcolumns = filter(lambda x: x.name not in view.exclude, vcolumns)
            args = (view.name or self, vcolumns)
            
            if 'doc' not in kwargs:
                kwargs['doc'] = self._doc
            if 'grant' not in kwargs:
                kwargs['grant'] = self._grant
            if 'depends' not in kwargs:
                kwargs['depends'] = (self._name,)                
            else:
                if self._name not in kwargs['depends']:
                    kwargs['depends'] = kwargs['depends'] + (self._name,)
            view = _GsqlView(*args, **kwargs)
            if self._schemas:
                view._set_schemas(self._schemas)
        return view
        
    def _format_column(self, column):
        cconstraints = column.constraints
        if isinstance(column, PrimaryColumn):
            cconstraints = ('PRIMARY KEY',) + cconstraints
        if column.references is not None:
            cconstraints = ('REFERENCES %s' % column.references,) + \
                           cconstraints
        constraints = string.join(cconstraints, ' ')
        if column.default:
            default = ' DEFAULT %s' % column.default
        else:
            default = ''
        result = '%s %s %s%s' % (self._column_column(column),
                                 _gsql_format_type(column.type),
                                 constraints, default)
        return result

    def _format_column_doc(self, column):
        full_column = self._full_column_name(column)
        return "COMMENT ON COLUMN %s IS '%s';\n" % \
               (full_column.name, column.doc)

    def _format_index(self, index_spec):
        columns, options = index_spec
        def strip(name):
            return name.split('.')[-1]
        columns = [strip(c) for c in columns]
        columns_string = string.join(columns, ', ')
        columns_name = string.join(columns, '_')
        name = '%s__%s__index' % (self._name, columns_name,)
        method_spec = (isinstance(options, dict) and options.get('method'))
        if method_spec:
            method = ' USING %s' % (method_spec,)
        else:
            method = ''
        return "CREATE INDEX %s ON %s%s (%s);\n" % (name, self._name, method, columns_string,)

    def _format_rule(self, action):
        laction = string.lower(action)
        body = self.__dict__['_on_'+laction]
        if body is None:
            result = ''
        else:
            result = 'CREATE OR REPLACE RULE %s_%s AS ON %s TO %s DO %s;\n' % \
                     (self._name, laction[:3], action, self._name, body)
        return result

    def _format_init_values(self, init_values):
        insert_string = 'INSERT INTO %s (%s) VALUES (%%s);\n' % \
                        (self._name, string.join(self._init_columns, ','))
        init_inserts = [insert_string % string.join(v, ',')
                        for v in init_values]
        return string.join(init_inserts)

    def name(self):
        """Vrať jméno tabulky zadané v konstruktoru."""
        return self._name
    
    def extra_names(self):
        names = []
        for c in self._columns:
            if isinstance(c.type, pytis.data.Serial):
                cname = c.name.split('.')[-1]
                names.append('%s_%s_seq' % (self._name, cname,))
        return names

    def columns(self):
        """Vrať specifikaci sloupců zadanou v konstruktoru."""
        return self._columns

    def key_columns(self):
        """Vrať seznam názvů klíčových sloupců."""
        kcols = []
        if len(self._key_columns) > 0:
            for c in self._key_columns:
                if isinstance(c, Column):
                    kcols.append(self._full_column_name(c).name)
                elif isinstance(c, basestring):
                    kcols.append("%s.%s" % (self._name, c))
        if len(kcols) == 0:
            for c in self._columns:
                if isinstance(c, PrimaryColumn):
                    kcols.append(self._full_column_name(c).name)
        return kcols        
    
    def _output(self, _re=False, _all=False):
        if not _re:
            columns = map(self._format_column, self._columns)
            columns = string.join(columns, ',\n        ')
            if self._sql:
                columns = columns + ',\n        %s' % self._sql
            columns = '        %s\n' % columns
            if self._inherits:
                inherits = ' INHERITS (%s)' % string.join(self._inherits, ',')
            else:
                inherits = ''
            if self._with_oids:
                with_oids = ' WITH OIDS'
            else:
                with_oids = ' WITHOUT OIDS'
            if self._tablespace:
                tablespace = ' TABLESPACE %s' % self._tablespace
            else:
                tablespace = ''
        result = ''
        if not _re:
            result = result + ('CREATE TABLE %s (\n%s)%s%s%s;\n' %
                               (self._name, columns, inherits, with_oids,
                                tablespace))
        if self._doc is not None:
            doc = "COMMENT ON TABLE %s IS '%s';\n" % \
                  (self._name, _gsql_escape(self._doc))
            result = result + doc
        result = result + self._revoke_command()
        for g in self._grant:
            result = result + self._grant_command(g)
        for c in self._columns:
            ct = c.type
            cn = self._column_column(c)
            if isinstance(ct, basestring) and ct.lower() == 'serial' \
               or ct.__class__ == pytis.data.Serial:
                seqname = "%s_%s_seq" % (self._name, cn)
                for g in self._grant:
                    if g[0].lower() in ('insert', 'all'):                    
                        result = result + self._grant_command(('usage', g[1],), seqname)
            if c.doc is not None:
                result = result + self._format_column_doc(c)
            if c.index is True:
                result = result + self._format_index(((c.name,), {},))
            elif isinstance(c.index, dict):
                result = result + self._format_index(((c.name,), c.index,))
            elif c.index is not None:
                raise ProgramError("Invalid column index specification",
                                   (self._name, c.name, c.index,))
        for index_spec in self._indexes:
            result = result + self._format_index(index_spec)
        for action in 'INSERT', 'UPDATE', 'DELETE':
            result = result + self._format_rule(action)
        if not _re and _all:
            result = result + self._format_init_values(self._init_values)
        if self._upd_log_trigger:
            keys = ','.join([_gsql_column_table_column(k)[1]
                             for k in self.key_columns()])
            result = result + ('CREATE TRIGGER %s_ins_log AFTER INSERT ON '
                               '%s FOR EACH ROW EXECUTE PROCEDURE '
                               '%s("%s");\n'
                               'CREATE TRIGGER %s_upd_log AFTER UPDATE ON '
                               '%s FOR EACH ROW EXECUTE PROCEDURE '
                               '%s("%s");\n'                               
                               'CREATE TRIGGER %s_del_log AFTER DELETE ON '
                               '%s FOR EACH ROW EXECUTE PROCEDURE '
                               '%s("%s");\n'
                               ) % (self._name, self._name,
                                    self._upd_log_trigger, keys,
                                    self._name, self._name,
                                    self._upd_log_trigger, keys,
                                    self._name, self._name,
                                    self._upd_log_trigger, keys)
        return result

    def outputall(self):
        return self.output(_re=False, _all=True)

    def reoutput(self):
        return self.output(_re=True)

    def db_update(self, connection):
        schemas = self._schemas
        if schemas is None:
            result = self._db_update(connection, 'public')
        else:
            result = ''
            for s in schemas:
                sname = s.split(',')[0].strip()
                result += self._db_update(connection, sname)
        return result

    def _db_update(self, connection, schema):
        name = self.name()
        query_args = dict(name=name, schema=schema)
        # Inheritance
        data = connection.query(
            ("select anc.relname from pg_class succ, pg_class anc, pg_inherits, pg_namespace "
             "where succ.relname='%(name)s' and pg_inherits.inhrelid=succ.oid and "
             "pg_inherits.inhparent=anc.oid and "
             "succ.relnamespace=pg_namespace.oid and "+
             "pg_namespace.nspname='%(schema)s'") % query_args)
        inherits = []
        for i in range(data.ntuples):
            inherits.append(data.getvalue(i, 0))
        if tuple(self._inherits) != tuple(inherits):
            result = '-- Inheritance mismatch, replacing the whole table\n'
            result = result + self.__class__.db_remove(name) + self.output()
            return result
        # Columns: name, type, primaryp, references, default,
        # constraints (unique, not null)
        result = ''
        data = connection.query(
            ("select attname, typname as typename, atttypmod as typelen, attnotnull as notnull "
             "from pg_attribute, pg_class, pg_namespace, pg_type "
             "where pg_class.relname='%(name)s' and "
             "pg_class.relnamespace=pg_namespace.oid and pg_namespace.nspname='%(schema)s' and "
             "pg_attribute.attrelid=pg_class.oid and not pg_attribute.attisdropped and pg_attribute.atttypid=pg_type.oid and pg_attribute.attnum>0 and pg_attribute.attislocal") % query_args)
        fnames = [data.fname(j) for j in range(1, data.nfields)]
        dbcolumns = {}
        for i in range(data.ntuples):
            cname = data.getvalue(i, 0)
            other = {}
            for j in range(1, data.nfields):
                k, v = fnames[j-1], data.getvalue(i, j)
                other[k] = v
            dbcolumns[cname] = other
        data = connection.query(
            ("select count(*) from pg_index, pg_class, pg_namespace "
             "where pg_class.relname='%(name)s' and "
             "pg_class.relnamespace=pg_namespace.oid and pg_namespace.nspname='%(schema)s' and "
             "pg_index.indrelid=pg_class.oid and pg_index.indisunique and pg_index.indkey[1] is not null") % query_args)
        if data.getvalue(0, 0) != 0:
            result = (result +
                      _gsql_warning("Can't handle multicolumn indexes in %s" %
                                    name))
        data = connection.query(
                ("select attname as column, indisprimary as primary, indisunique as unique "
                 "from pg_index, pg_class, pg_namespace, pg_attribute "
                 "where pg_class.relname='%(name)s' and "
                 "pg_class.relnamespace=pg_namespace.oid and pg_namespace.nspname='%(schema)s' and "
                 "pg_index.indrelid=pg_class.oid and pg_attribute.attrelid=pg_class.oid and pg_attribute.attnum=pg_index.indkey[0] and pg_index.indkey[1] is null and pg_attribute.attnum>0 and pg_attribute.attislocal") % query_args)
        for i in range(data.ntuples):
            cname = data.getvalue(i, 0)
            cproperties = dbcolumns[cname]
            cproperties['primaryp'] = cproperties.get('primaryp') or data.getvalue(i, 1)
            cproperties['uniquep'] = cproperties.get('uniquep') or data.getvalue(i, 2)
        data = connection.query(
                ("select attname, adsrc from pg_attribute, pg_attrdef, pg_class, pg_namespace "
                 "where pg_class.relname='%(name)s' and "
                 "pg_class.relnamespace=pg_namespace.oid and pg_namespace.nspname='%(schema)s' and "
                 "pg_attribute.attrelid=pg_class.oid and pg_attrdef.adrelid=pg_class.oid and pg_attribute.attnum=pg_attrdef.adnum and pg_attribute.attnum>0 and pg_attribute.attislocal") % query_args)
        for i in range(data.ntuples):
            dbcolumns[data.getvalue(i, 0)]['default'] = data.getvalue(i, 1)
        columns = list(copy.copy(self._columns))
        def column_changed(column, dbcolumn):
            def normalize(s):
                s = string.lower(string.strip(s))
                s = re.sub('  +', ' ', s)
                return s
            cname = column.name
            primaryp = isinstance(column, PrimaryColumn)
            # type
            default = column.default
            constraints = map(normalize, column.constraints)
            ct = column.type
            if isinstance(ct, basestring):
                TYPE_ALIASES = {'int2': 'smallint'}
                if ct != dbcolumn['typename'] and ct != TYPE_ALIASES.get(dbcolumn['typename']):
                    sys.stdout.write(
                        _gsql_warning('Possible mismatch in raw column type of %s(%s): %s x %s' %
                                      (name, cname, ct, dbcolumn['typename'],)))
            else:
                if ct.__class__ == pytis.data.Serial:
                    if default is None:
                        default = ('nextval(\'%s_%s_seq\'::regclass)'
                                   % (name, _gsql_column_table_column(cname)[1]))
                    ctclass = pytis.data.Integer
                    if not primaryp:
                        constraints.append('not null')
                else:
                    for c in ct.__class__.__mro__:
                        if c in (pytis.data.Boolean,
                                 pytis.data.Date,
                                 pytis.data.DateTime,
                                 pytis.data.Float,
                                 pytis.data.Integer,
                                 pytis.data.LTree,
                                 pytis.data.Oid,
                                 pytis.data.String,
                                 pytis.data.Time,
                                 ):
                            ctclass = c
                            break
                    else:
                        ctclass = ct.__class__
                if ctclass is pytis.data.Boolean:
                    if default.lower() in ("'f'", "'false'", "false"):
                        default = 'false'
                    elif default.lower() in ("'t'", "'true'", "true"):
                        default = 'true'
                TYPE_MAPPING = {'bool': pytis.data.Boolean,
                                'bytea': pytis.data.Binary,
                                'bpchar': pytis.data.String,
                                'char': pytis.data.String,
                                'date': pytis.data.Date,
                                'time': pytis.data.Time,
                                'smallint': pytis.data.Integer,
                                'int2': pytis.data.Integer,
                                'int4': pytis.data.Integer,
                                'int8': pytis.data.Integer,
                                'bigint': pytis.data.Integer,
                                'numeric': pytis.data.Float,
                                'ltree': pytis.data.LTree,
                                'oid': pytis.data.Oid,
                                'name': pytis.data.String,
                                'text': pytis.data.String,
                                'timestamp': pytis.data.DateTime,
                                'timestamptz': pytis.data.DateTime,
                                'varchar': pytis.data.String}
                if (ctclass is not TYPE_MAPPING[dbcolumn['typename']]):
                    return ('Type mismatch (%s x %s)' %
                            (ctclass, TYPE_MAPPING[dbcolumn['typename']]))
                if column.type.__class__ == pytis.data.String:
                    l = column.type.maxlen()
                    if l:
                        if l != dbcolumn['typelen'] - 4:
                            return ('Type mismatch (length: %s x %s)' %
                                    (l, dbcolumn['typelen']))
                    else:
                        if dbcolumn['typename'] != 'text':
                            return ('Type mismatch (text x %s)' %
                                    dbcolumn['typename'])
            # not null
            if xor(primaryp or 'not null' in constraints,
                   dbcolumn.get('notnull')):
                return 'Not null status mismatch'
            # unique
            if xor(primaryp or 'unique' in constraints,
                   dbcolumn.get('uniquep')):
                message = 'Unique status mismatch'
                return message
            # default
            MAPPINGS = {'user': '"current_user"()',
                        'session_user': '"session_user"()'}
            if default in MAPPINGS:
                default = MAPPINGS[default]
            dbcolumn_default = dbcolumn.get('default')
            if dbcolumn_default is not None and not dbcolumn.get('primaryp'):
                pos = dbcolumn_default.find('::')
                if pos != -1:
                    dbcolumn_default = dbcolumn_default[:pos]
            if default != dbcolumn_default:
                return ('Default value mismatch (%s x %s)' %
                        (default, dbcolumn.get('default')))
            # primaryp
            if xor(primaryp, dbcolumn.get('primaryp')):
                return 'Primary status mismatch'
            # OK
            return ''
        def tmp_col_name():
            i = 0
            while True:
                name = 'tmp%d' % i
                if name not in dbcolumns:
                    return name
                i = i + 1
        def column_name(column):
            return _gsql_column_table_column(column.name)[1]
        for cname, other in dbcolumns.items():
            i = position(cname, columns, key=column_name)
            if i is None:
                result = result + ("ALTER TABLE %s DROP COLUMN %s;\n" %
                                   (name, cname))
            else:
                changed = column_changed(columns[i], other)
                if changed:
                    tmp = tmp_col_name()
                    result = (
                        result +
                        ("-- Column `%s' changed: %s\n" % (cname, changed)) +
                        ('ALTER TABLE %s RENAME COLUMN %s TO %s;\n' %
                         (name, cname, tmp)) +
                        ('ALTER TABLE %s ADD COLUMN %s;\n' %
                         (name, self._format_column(columns[i]))) +
                        ('UPDATE %s SET %s=%s;\n' % (name, cname, tmp)) +
                        ("ALTER TABLE %s DROP COLUMN %s;\n" % (name, tmp)))
                del columns[i]
        for c in columns:
            result = result + ('ALTER TABLE %s ADD COLUMN %s;\n' %
                               (name, self._format_column(c)))
        # Triggers
        pass
        # Raw SQL
        if self._sql is not None:
            result = (result +
                      _gsql_warning(
                        'SQL statements present, not checked in %s' % name))
        # Initial values
        init_values = []
        for values in self._init_values:
            if tuple(values) == ('now()',):
                result = (result +
                          _gsql_warning(
                            "`now()' initial value not checked in %s" % name))
                continue
            spec = []
            for col, value in zip(self._init_columns, values):
                if value.lower() == 'null':
                    spec.append('%s is %s' % (col, value,))
                else:
                    spec.append('%s=%s' % (col, value,))
            specstring = string.join(spec, ' AND ')
            query = "SELECT COUNT(*) FROM %s WHERE %s" % (name, specstring)
            data = connection.query(query)
            if data.getvalue(0, 0) == 0:
                init_values.append(values)
        result = result + self._format_init_values(init_values)
        # Done
        if not result:
            result = super(_GsqlTable, self).db_update(connection)
        return result

    def convert(self):
        spec_name = self._convert_name(new=True)
        superclass = 'db.Base_LogSQLTable' if self._upd_log_trigger else 'sql.SQLTable'
        items = ['class %s(%s):' % (spec_name, superclass,)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        table_name = repr(self._name.lower())
        if table_name == "'cms_users'" and _GsqlConfig.application == 'pytis':
            table_name = "'pytis_cms_users'"
        items.append('    name = %s' % (table_name,))
        self._convert_schemas(items)
        items.append('    fields = (')
        for column in self._columns:
            items.append(self._convert_indent(self._convert_column(column), 14) + ',')
        items.append('             )')
        inherits = [self._convert_name(name) for name in (self._inherits or ())]
        inherits_string = string.join(inherits, ', ')
        if inherits_string:
            inherits_string += ','
            items.append('    inherits = (%s)' % (inherits_string,))
        if self._tablespace:
            items.append('    tablespace = %s' % (repr(self._tablespace),))
        init_columns = [c.name if isinstance(c, Column) else c for c in self._init_columns]
        init_values = self._init_values
        if not init_columns and init_values:
            init_columns = [c.name for c in self.columns]
        if init_values:
            items.append('    init_columns = %s' % (repr(tuple(init_columns)),))
            items.append('    init_values = (')
            for row in init_values:
                if row:
                    row_values = string.join([self._convert_value(v) for v in row], ', ')
                    items.append('                   (%s,),' % (row_values,))
            items.append('                  )')
        items.append('    with_oids = %s' % (repr(self._with_oids),))
        unique = ''
        check = []
        sql = self._sql
        while sql:
            sql = sql.strip()
            start = sql.find('(')
            if start < 0:
                break
            level = 1
            end = start + 1
            l = len(sql)
            while end < l:
                if sql[end] == '(':
                    level += 1
                elif sql[end] == ')':
                    level -= 1
                    if level <= 0:
                        break
                end += 1
            if level > 0:
                break
            action = sql[:start].rstrip().lower()
            def trim(sql):
                sql = sql[end+1:].strip()
                if sql and sql[0] == ',':
                    sql = sql[1:].lstrip()
                return sql
            if action == 'unique':
                components = sql[start+1:end].split(',')
                components = ["'%s'" % (c.strip(),) for c in components]
                unique += "(%s,)," % (string.join(components, ', '),)
                sql = trim(sql)
            elif action == 'check':
                check.append(sql[start+1:end])
                sql = trim(sql)
            else:
                break
        if self._indexes:
            items.append('#XXX: %s' % (self._indexes,))
        if unique:
            items.append('    unique = (%s)' % (unique,))
        if check:
            check_string = string.join([repr(c) for c in check], ', ') + ','                
            items.append('    check = (%s)' % (check_string,))
        if sql:            
            items.append('#XXX: %s' % (sql.replace('\n', '\n#'),))
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        def add_rule(kind, command):
            if command:
                items.append('    def on_%s_also(self):' % (kind,))
                items.append ('        return ("%s",)' % (command,))
        add_rule('insert', self._on_insert)
        add_rule('update', self._on_update)
        add_rule('delete', self._on_delete)
        result = string.join(items, '\n') + '\n'
        return result
    
class Select(_GsqlSpec):
    """Specifikace SQL selectu."""

    def __init__(self, relations, include_columns=(),
                 group_by=None, having=None, order_by=None, limit=None,
                 **kwargs):
        """Inicializuj instanci.
        Argumenty:

          relations -- sekvence instancí třídy SelectRelation nebo SelectSet.
          include_columns -- seznam instancí třídy ViewColumn, které budou
            přidány ke sloupcům z relations (typicky výrazové sloupce).
          group_by -- string pro klauzuli GROUP BY.  
          having -- string pro klauzuli HAVING.  
          order_by -- string pro klauzuli GROUP BY.  
          limit -- hodnota limit pro select.  
        """
        super(Select, self).__init__(None, **kwargs)
        self._relations = relations
        self._group_by = group_by
        self._having = having
        self._order_by = order_by
        self._limit = limit
        self._include_columns = include_columns
        self._columns = []
        self._set = self._is_set()

    def _is_set(self):        
        first = self._relations[0]
        for r in self._relations:
            if not sameclass(r, first):
                raise ProgramError('Different classes in relation sequence.')
        if isinstance(first, SelectSet):
            if self._group_by:
                raise ProgramError('Bad Syntax: group by')
            if self._having:
                raise ProgramError('Bad Syntax: having')
            if self._include_columns:
                raise ProgramError('Bad Syntax: include_columns')               
            return True
        else:
            if self._relations[0].jointype != JoinType.FROM:
                raise ProgramError('Bad Syntax: First join must be FROM')
            return False
        
    def _column_column(self, column):
        return _gsql_column_table_column(column.name)[1]

    def _format_column(self, column):
        if isinstance(column, basestring):
            cname = alias = column
        else:
            if column.sql:
                cname = column.sql
            else:    
                cname = column.name
            alias = column.alias
        if type is None:
            cname = 'NULL'
        elif isinstance(type, pytis.data.Type):
            cname = 'NULL::%s' % _gsql_format_type(type)
        elif isinstance(type, basestring):
            cname = 'NULL::%s' % type
        return '%s AS %s' % (cname, alias)

    def _format_columns(self, indent=0):
        COLSEP = ',\n%s' % (' '*(indent+1))
        result = COLSEP.join([self._format_column(c)
                              for c in self._columns])
        return result

    def _format_relations(self, indent=1):
        def format_relation(i,rel):
            jtype = rel.jointype
            if isinstance(rel.relation, Select):
                sel = rel.relation.format_select(indent=indent+1)
                sel = sel.strip().strip('\n')
                relation = '\n%s(%s)' % (' '*(indent+1), sel)
            elif (isinstance(rel, SelectRelation) and
                  rel.schema is not None):
                relation = '%s.%s' % (rel.schema, rel.relation,)
            else:
                relation = rel.relation
            alias = rel.alias or ''
            if i == 0 or rel.condition is None:
                condition = ''
            else:    
                condition = rel.condition
            return JoinType.TEMPLATES[jtype] % (relation, alias, condition)
        # První relace je FROM a podmínka nebude použita
        wherecondition = self._relations[0].condition
        joins = [format_relation(i,r) for i,r in enumerate(self._relations)]
        result = '\n '.join(joins)
        if wherecondition:
            result = '%s\n WHERE %s' % (result, wherecondition)
        return result


    def set_columns(self, relation_columns):
        self._relation_columns = relation_columns
        vcolumns = []
        aliases = []
        def make_columns(cols, column_aliases, rel_alias):
            for c in cols:
                if isinstance(c, ViewColumn):
                    if c.alias:
                        cname = c.alias
                    else:
                        cname = c.name
                else:                    
                    cname = self._column_column(c)
                if '*' in r.exclude_columns or cname in r.exclude_columns:
                    continue
                calias = assoc(cname, column_aliases)
                if not calias:
                    calias = cname
                else:
                    calias = calias[1]
                if calias not in aliases:
                    aliases.append(calias)
                    vname = '%s.%s' % (rel_alias, cname)                    
                    vcolumns.append(ViewColumn(vname, alias=calias))
                else:
                    raise ProgramError('Duplicate column name', calias)
        if self._set:
            for r in self._relations:
                vcolumns = r.select.set_columns(self._relation_columns)
                self._columns.append(vcolumns)
        else:
            for r in self._relations:
                rel_alias = r.alias
                column_aliases = r.column_aliases
                if isinstance(r.relation, Select):
                    r.relation.set_columns(self._relation_columns)
                    columnlist = r.relation.columns()                    
                else:    
                    if '*' in r.exclude_columns:
                        continue
                    columnlist = self._relation_columns[r.relation]
                make_columns(columnlist, column_aliases, rel_alias)            
            for c in self._include_columns:
                if c.alias not in aliases:
                    aliases.append(c.alias)
                    vcolumns.append(c)
                else:
                    raise ProgramError('Duplicate column name', c.alias, aliases)
            self._columns = vcolumns
        return self._columns

    def columns(self):
        if self._set:
            columns = self._columns[0]
        else:
            columns = self._columns
        return [ViewColumn(c.alias) for c in columns]           

    def sort_columns(self, aliases):
        # Check length and column aliases
        colaliases = [c.alias for c in self._columns]
        missed = set(aliases) ^ set(colaliases)
        if len(missed) != 0:
            names = ' | '.join(missed)
            raise ProgramError('Different columns in SelectSet', names)            
        # Reorder
        columns = []
        for a in aliases:
            col = find(a, self._columns, key=lambda c: c.alias)
            if col is None:
                raise ProgramError("Can't find columns alias in SelectSet", a)
            else:
                columns.append(col)
        self._columns = columns        

    def format_select(self, indent=0):
        if not self._set:
            relations = self._format_relations(indent=indent)
            columns = self._format_columns(indent=indent)
            select = '%sSELECT\n\t%s\n %s\n' % (' '*(indent+1), columns,
                                                relations)
            if self._group_by:
                select = '%s GROUP BY %s\n' % (select, self._group_by)
            if self._having:
                select = '%s HAVING %s\n' % (select, self._having)
        else:
            #self.sort_set_columns()
            selects = []
            aliases = [c.alias for c in self._columns[0]]
            for r in self._relations:
                r.sort_columns(aliases)
                selects.append(r.format_select(indent=indent))
            select = ''.join(selects)
        if self._order_by:
            select = '%s ORDER BY %s\n' % (select, self._order_by)
        if self._limit:
            select = '%s LIMIT %s\n' % (select, self._limit)
        return select

    def _output(self):
        return ''

    def _convert_raw_columns(self, columns):
        string_columns = ["'%s'" % (c.strip().replace('\\', '\\\\').replace("'", "\\'").replace('\n', '\\n'),) for c in columns.split(',')]
        return string.join(string_columns, ', ')

    def _convert_raw_condition(self, condition, as_object=False):
        if not condition:
            return ''
        converted = "'%s'" % (_gsql_escape(condition or '').replace('\n', '\\n'),)
        if as_object:
            converted = 'sql.gR(%s)' % (converted,)
        return converted

    def _convert_relation_name(self, relation):
        alias = relation.alias
        if not alias:
            if isinstance(relation, SelectRelation):
                alias = relation.relation
            else:
                alias = relation.name
        name = self._convert_id_name(alias.lower())
        return self._convert_local_name(name)
 
    def _convert_select_columns(self, column_ordering=None):
        column_spec = []
        for r in self._relations:
            relname = self._convert_relation_name(r)
            aliases = list(r.column_aliases)
            exclude = r.exclude_columns or ()
            if isinstance(exclude, basestring):
                exclude = (exclude,)
            exclude = tuple([c.lower() for c in exclude])
            if isinstance(r.relation, Select):
                if not r.alias:
                    column_spec.append('XXX:selnone:%s' % (r.relation,))
            elif '*' not in exclude:
                subspec = []
                for c in self._relation_columns[r.relation]:
                    if isinstance(c, basestring):
                        continue
                    if isinstance(c.name, (tuple, list,)):
                        continue
                    if c.name.lower() in exclude:
                        continue
                    if isinstance(c, ViewColumn) and c.sql:
                        if r.alias and c.alias:
                            subspec.append('%s.c.%s' % (r.alias, c.alias,))
                        else:
                            subspec.append('XXX:sql:%s' % (c,))
                    cname = c.name
                    plain_name = cname
                    pos = plain_name.rfind('.')
                    if pos >= 0 and re.match('^[.a-zA-Z_ ]+$', plain_name):
                        plain_name = plain_name[pos+1:]
                    if isinstance(c, ViewColumn) and c.alias:
                        if c.alias != plain_name:
                            aliases.append((plain_name, c.alias,))
                if subspec:
                    column_spec.append("[%s]" % (string.join(subspec, ', '),))
            if exclude or aliases:
                if '*' in exclude:
                    continue
                colist = string.join(["'%s'" % (c,) for c in exclude], ', ')
                if exclude:
                    spec = 'cls._exclude(%s, %s)' % (relname, colist,)
                else:
                    spec = '%s.c' % (relname,)
                if aliases:
                    alias_spec = string.join(['%s=%s.c.%s' % (self._convert_local_name(alias), relname, name,)
                                              for name, alias in aliases],
                                             ', ')
                    spec = 'cls._alias(%s, %s)' % (spec, alias_spec,)
                column_spec.append(spec)
            else:
                column_spec.append('cls._exclude(%s)' % (relname,))
        if self._include_columns:
            simple_relations = [r.relation if r.alias is None else r.alias for r in self._relations
                                if isinstance(r, SelectRelation) and
                                isinstance(r.relation, basestring) and
                                r.relation.find('(') == -1]
            included = [self._convert_select_column(c, simple_relations) for c in self._include_columns]
            column_spec.append('[%s]' % (string.join(included, ',\n    '),))
        result = string.join(column_spec, ' +\n    ')
        if column_ordering is not None:
            result = 'sql.reorder_columns(%s, %s)' % (result, column_ordering,)
        return result

    def _convert_select_column(self, column, simple_relations):
        if isinstance(column, basestring):
            cname = column
            alias = None
        else:
            if column.sql:
                cname = column.sql
            else:    
                cname = column.name
        self._convert_add_raw_dependencies(cname)
        plain_name = cname
        pos = plain_name.rfind('.')
        if pos >= 0 and re.match('^[.a-zA-Z_ ]+$', plain_name):
            plain_name = plain_name[pos+1:].lower()
        alias = None if (column.alias.lower() == plain_name and cname == plain_name) else column.alias.lower()
        if alias is None:
            cname, alias = self._convert_unalias_column(cname)
        match = re.match('^([a-zA-Z_][a-zA-Z_0-9]*)\.([a-zA-Z_][a-zA-Z_0-9]*) *$', cname)
        if match and match.group(1) in simple_relations and match.group(2) != 'oid':
            cstring = '%s.c.%s' % (self._convert_local_name(match.group(1).lower()),
                                   match.group(2).lower(),)
        else:
            cstring = 'sql.gL("%s")' % (self._convert_literal(cname),)
        if alias:
            cstring += ".label('%s')" % (alias.strip(),)
        return cstring

    def _convert_unalias_column(self, cname):
        alias = None
        c = cname.split()
        if len(c) >= 3 and c[-2] == 'AS':
            alias = c[-1].lower()
            cname = string.join(c[:-2])
        return cname, alias

    def _convert_add_definition(self, definitions, d, level, split=False):
        indentation = '    ' * level
        if split:
            indented = string.join([indentation + dd for dd in d.split('\n')], '\n')
        else:
            indented = indentation + d
        definitions.append(indented)
        
    def _convert_relations(self, definitions, level):
        for r in self._relations:
            if isinstance(r.relation, Select):
                return self._convert_complex_relations(definitions, level)
        return self._convert_simple_relations(definitions, level)

    def _convert_simple_relations(self, definitions, level):
        def convert_relation(i, rel, prev_result):
            jtype = rel.jointype
            noalias = False
            if isinstance(rel.relation, Select):
                raise Exception("Program error")
            elif (isinstance(rel, SelectRelation) and
                  rel.relation[0] == '(' and
                  (rel.relation.lower().find('from') >= 0 or
                   rel.relation.lower().find('values') >= 0)):  # apparently a subselect
                relation = self._convert_relation_name(rel)
                d = ('%s = sqlalchemy.select(["*"], from_obj=["%s AS %s"])' %
                     (self._convert_local_name(self._convert_id_name(relation)),
                      rel.relation.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n'),
                      rel.alias,))
            elif (isinstance(rel, SelectRelation) and
                  rel.relation.find('(') >= 0):  # apparently a function call
                relation = self._convert_relation_name(rel)
                funcsig = rel.relation.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                local_name = self._convert_local_name(self._convert_id_name(relation))
                if rel.relation.startswith('dblink'):
                    expr = ('sqlalchemy.alias(sqlalchemy.literal("%s"), \'%s\')' %
                            (funcsig, (rel.alias or local_name),))
                else:
                    expr = ('sqlalchemy.select(["*"], from_obj=["%s"]).alias(\'%s\')' %
                            (funcsig, (rel.alias or local_name),))
                d = ('%s = %s' % (local_name, expr,))
                noalias = True
            elif (isinstance(rel, SelectRelation) and
                  rel.schema is not None):
                relation = self._convert_relation_name(rel)
                self._add_conversion_dependency(rel.relation, rel.schema)
                d = "%s = sql.object_by_name('%s.%s')" % (self._convert_local_name(relation),
                                                      rel.schema, rel.relation,)
            else:
                relation = self._convert_relation_name(rel)
                rrelation = rel.relation
                match = re.match('^([a-zA-Z_][a-zA-Z_0-9]*)\.([a-zA-Z_][a-zA-Z_0-9]*)$', rrelation)
                if match:
                    selector = 'sql.object_by_name'
                    rschema, dependency = match.groups()
                    d = "%s = %s('%s')" % (self._convert_local_name(relation), selector, rrelation.lower(),)
                elif rrelation.startswith('pg_'):
                    dependency = rrelation
                    rschema = None
                    d = "%s = sql.gO('%s')" % (self._convert_local_name(relation), rrelation.lower(),)
                else:
                    dependency = rrelation
                    rschema = None
                    d = "%s = sql.t.%s" % (self._convert_local_name(relation), self._convert_name(rrelation, short=True),)
                self._add_conversion_dependency(dependency, rschema)
            if rel.alias and not noalias:
                if d is None:
                    d = '%s = %s' % (self._convert_local_name(self._convert_id_name(rel.alias.lower())), relation,)
                    relation = rel.alias.lower()
                d += ".alias('%s')" % (rel.alias.lower(),)
            if d:
                self._convert_add_definition(definitions, d, level)
            if i == 0 or rel.condition is None:
                condition = ''
            else:    
                condition = rel.condition
            relation = self._convert_local_name(relation)
            if jtype == JoinType.FROM:
                result = relation
            elif jtype == JoinType.INNER:
                result = '%s.join(%s, %s)' % (prev_result, relation, self._convert_raw_condition(condition, True),)
            elif jtype == JoinType.LEFT_OUTER:
                result = '%s.outerjoin(%s, %s)' % (prev_result, relation, self._convert_raw_condition(condition, True),)
            elif jtype == JoinType.CROSS and not condition:
                result = '%s.join(%s, sqlalchemy.sql.true())' % (prev_result, relation,)
            elif jtype == JoinType.FULL_OUTER:
                result = 'sql.FullOuterJoin(%s, %s, %s)' % (prev_result, relation, self._convert_raw_condition(condition, True))
            else:
                result = '%s.XXX:%s(%s, %s)' % (prev_result, jtype, relation, self._convert_raw_condition(condition),)
            return result
        result = ''
        for i, r in enumerate(self._relations):
            result = convert_relation(i, r, result)
        condition = self._convert_raw_condition(self._relations[0].condition)
        return result, condition

    def _convert_complex_relations(self, definitions, level):
        def convert_relation(rel, last_relation):
            jtype = rel.jointype
            noalias = False
            if isinstance(rel.relation, Select):
                relation = rel.relation._convert_select(definitions, level)
                d = None
            elif (isinstance(rel, SelectRelation) and
                  rel.relation[0] == '(' and
                  (rel.relation.lower().find('from') >= 0 or
                   rel.relation.lower().find('values') >= 0)):  # apparently a subselect
                relation = self._convert_relation_name(rel)
                d = ('%s = sqlalchemy.select(["*"], from_obj=["%s AS %s"])' %
                     (self._convert_local_name(self._convert_id_name(relation)),
                      rel.relation.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n'),
                      rel.alias,))
            elif (isinstance(rel, SelectRelation) and
                  rel.relation.find('(') >= 0):  # apparently a function call
                relation = self._convert_relation_name(rel)
                funcsig = rel.relation.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
                local_name = self._convert_local_name(self._convert_id_name(relation))
                if rel.relation.startswith('dblink'):
                    expr = ('sqlalchemy.alias(sqlalchemy.literal("%s"), \'%s\')' %
                            (funcsig, (rel.alias or local_name),))
                else:
                    expr = ('sqlalchemy.select(["*"], from_obj=["%s"]).alias(\'%s\')' %
                            (funcsig, (rel.alias or local_name),))
                d = ('%s = %s' % (local_name, expr,))
                noalias = True
            elif (isinstance(rel, SelectRelation) and
                  rel.schema is not None):
                relation = self._convert_relation_name(rel)
                self._add_conversion_dependency(rel.relation, rel.schema)
                d = "%s = sql.object_by_name('%s.%s')" % (self._convert_local_name(relation),
                                                      rel.schema, rel.relation,)
            else:
                relation = self._convert_relation_name(rel)
                rrelation = rel.relation
                match = re.match('^([a-zA-Z_][a-zA-Z_0-9]*)\.([a-zA-Z_][a-zA-Z_0-9]*)$', rrelation)
                if match:
                    selector = 'sql.object_by_name'
                    rschema, dependency = match.group()
                    d = "%s = %s('%s')" % (self._convert_local_name(relation), selector, rrelation,)
                elif rrelation.startswith('pg_'):
                    dependency = rrelation
                    rschema = None
                    d = "%s = sql.gO('%s')" % (self._convert_local_name(relation), rrelation.lower(),)
                else:
                    dependency = rrelation
                    rschema = None
                    d = "%s = sql.t.%s" % (self._convert_local_name(relation), self._convert_name(rrelation, short=True),)
                self._add_conversion_dependency(dependency, rschema)
            if rel.alias and not noalias:
                if d is None:
                    d = '%s = %s' % (self._convert_local_name(self._convert_id_name(rel.alias)),
                                     relation,)
                    relation = rel.alias
                d += ".alias('%s')" % (rel.alias,)
            if d:
                self._convert_add_definition(definitions, d, level)
            if last_relation is None or rel.condition is None:
                condition = ''
            else:    
                condition = rel.condition
            if last_relation is None and jtype != JoinType.FROM:
                raise Exception("Error", (self, jtype,))
            last_relation = self._convert_local_name(last_relation)
            relation = self._convert_local_name(relation)            
            if jtype == JoinType.FROM:
                result = relation
            elif jtype == JoinType.INNER:
                c = self._convert_raw_condition(condition, True)
                result = '%s.join(%s, %s)' % (last_relation, relation, c,)
            elif jtype == JoinType.LEFT_OUTER:
                c = self._convert_raw_condition(condition, True)
                result = '%s.outerjoin(%s, %s)' % (last_relation, relation, c,)
            elif jtype == JoinType.CROSS and not condition:
                result = '%s.join(%s, sqlalchemy.sql.true())' % (last_relation, relation,)
            elif jtype == JoinType.FULL_OUTER:
                c = self._convert_raw_condition(condition, True)
                result = 'sql.FullOuterJoin(%s, %s, %s)' % (last_relation, relation, c,)
            else:
                c = self._convert_raw_condition(condition)
                result = '%s.XXX:%s(%s, %s)' % (last_relation, jtype, relation, c,)
            if result == relation:
                return relation
            dname = 'join_%s_%s' % (last_relation.rstrip('_'), relation.rstrip('_'),)
            if dname.startswith('join_join_'):
                dname = dname[5:]
            self._convert_add_definition(definitions, '%s = %s' % (self._convert_local_name(dname), result,),
                                         level)
            return dname
        last_relation = None
        for r in self._relations:
            last_relation = convert_relation(r, last_relation)
        condition = self._convert_raw_condition(self._relations[0].condition)
        return last_relation, condition
        
    def _convert_select(self, definitions, level, column_ordering=None):
        def select_n(prefix):
            n = 1
            if prefix == 'select':
                defprefix = 'def %s_' % (prefix,)
            else:
                defprefix = 'set_'
            for d in definitions:
                if d.lstrip().startswith(defprefix):
                    n += 1
            return '%s_%s' % (prefix, n,)
        if self._set:
            if column_ordering is not None:
                raise Exception('Double set', self)
            column_ordering = [c.alias.lower() for c in self._columns[0]]
            condition = ''
            for r in self._relations:
                if isinstance(r, SelectSet):
                    output = r.select._convert_select(definitions, level, column_ordering)
                    if r.settype:
                        assert condition
                        settype = r.settype.lower()
                        if settype == 'except':
                            settype += '_'
                        condition = 'sqlalchemy.%s(%s, %s)' % (settype, condition, output,)
                        select_name = select_n('set')
                        self._convert_add_definition(definitions, '%s = %s' % (select_name, condition,), level)
                        condition = select_name
                    else:
                        assert not condition, condition
                        condition = output
                else:
                    r._convert_select(definitions, level)
                    condition += 'XXX:select=%s' % (r,)
            if self._limit:
                # .limit() doesn't work well with aliases in sqlalchemy
                condition += 'XXX:limit=%d' % (self._limit,)
        else:
            select_name = select_n('select')
            self._convert_add_definition(definitions, 'def %s():' % (select_name,), level)
            relations, where_condition = self._convert_relations(definitions, level + 1)
            if self._limit:
                # .limit() doesn't work well with aliases in sqlalchemy
                where_condition = where_condition[:-1] + " LIMIT %d'" % (self._limit,)
            converted_columns = self._convert_select_columns(column_ordering)
            in_list = 0
            split_columns = []
            for c in converted_columns.split('\n'):
                indentation = '    ' + ' ' * in_list
                split_columns.append(indentation + c)
                if c.lstrip().startswith('['):
                    in_list += 1
                if c.rstrip(' +').endswith(']'):
                    in_list -= 1
            columns = string.join(split_columns, '\n')
            whereclause = ',\n        whereclause=%s' % (where_condition,) if where_condition else ''
            condition = ('sqlalchemy.select(\n    %s,\n        from_obj=[%s]%s\n        )' %
                         (columns, relations, whereclause,))
            if self._group_by:
                condition += '.group_by(%s)' % (self._convert_raw_columns(self._group_by),)
            if self._having:
                condition += '.having(%s)' % (self._convert_raw_condition(self._having),)
            self._convert_add_definition(definitions, '    return %s' % (condition,), level, True)
            condition = select_name + '()'
        if self._order_by:
            condition += '.order_by(%s)' % (self._convert_raw_columns(self._order_by),)
        return condition
     

class _GsqlViewNG(Select):
    """Specifikace view (nová)."""
    
    _SQL_NAME = 'VIEW'
    _PGSQL_TYPE = 'v'

    _INSERT = 'INSERT'
    _UPDATE = 'UPDATE'
    _DELETE = 'DELETE'
   
    def __init__(self, name, relations, schemas=None,
                 insert=(), update=(), delete=(),
                 insert_order=None, update_order=None, delete_order=None,
                 primary_column=None,
                 **kwargs):
        """Inicializuj instanci.
        Argumenty:

          name -- jméno view jako SQL string
          relations -- sekvence instancí třídy SelectRelation
          schemas -- není-li 'None', definuje schémata, ve kterých má být
            view vytvořeno, jde o sekvenci řetězců obsahujících textové
            definice postgresové search_path určující search_path nastavenou
            při vytváření view, view je samostatně vytvořeno pro každý
            z prvků této sekvence
          insert -- specifikace akce nad view při provedení operace INSERT.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po vložení předaných hodnot sloupců do tabulky
            prvního sloupce view.
          update -- specifikace akce nad view při provedení operace UPDATE.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po updatu předaných hodnot sloupců v tabulce
            prvního sloupce view.
          delete -- specifikace akce nad view při provedení operace DELETE.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po smazání daného záznamu z tabulky prvního sloupce
            view.
          insert_order -- None nebo sekvence názvů SelectRelation. Pokud je None,
            budou defaultní inserty v insert rulu provedeny pro jednotlivé
            relace v pořadí jejich uvedení, pokud je uvedena sekvence názvů,
            budou provedeny v uvedeném pořadí. Vynecháním názvu SelectRelation
            se docílí toho, že insert pro danou relaci nebude vůbec proveden.
          update_order -- None nebo sekvence názvů SelectRelation. Pokud je None,
            budou defaultní updaty v update rulu provedeny pro jednotlivé
            relace v pořadí jejich uvedení, pokud je uvedena sekvence názvů,
            budou provedeny v uvedeném pořadí. Vynecháním názvu SelectRelation
            se docílí toho, že update pro danou relaci nebude vůbec proveden.
          delete_order -- None nebo sekvence názvů SelectRelation. Pokud je None,
            budou defaultní delety v delete rulu provedeny pro jednotlivé
            relace v pořadí jejich uvedení, pokud je uvedena sekvence názvů,
            budou provedeny v uvedeném pořadí. Vynecháním názvu SelectRelation
            se docílí toho, že delete pro danou relaci nebude vůbec proveden.
        """
        #assert relations[0].jointype == JoinType.FROM
        super(ViewNG, self).__init__(relations, **kwargs)
        self._set_name(name)
        self._set_schemas(schemas)
        self._insert = insert
        self._update = update
        self._delete = delete
        self._insert_order = insert_order
        self._update_order = update_order
        self._delete_order = delete_order
        self._primary_column = primary_column
        self._columns = []

    def _format_rule(self, kind, table_keys):
        def relations(list_order):
            if list_order is None:
                rels = self._relations
            else:
                rels = []
                for r in list_order:
                    rel = find(r, self._relations, lambda x: x.relation)
                    if rel is not None and \
                       not isinstance(rel.relation, SelectRelation):
                        rels.append(rel)
            return rels
        def get_key_column(relation):
            key = relation.key_column
            if not key:
                try:
                    key = table_keys[relation.relation]
                except:
                    pass
            if isinstance(key, (tuple,list)):
                return _gsql_column_table_column(key[0])[1]
            else:
                return _gsql_column_table_column(key)[1]
        def get_default_body(kind):
            columns = self._columns
            body = []
            def make_table_name(r):
                table_name = r.relation
                if isinstance(r, SelectRelation) and r.schema is not None:
                    table_name = '%s.%s' % (r.schema, table_name,)
                return table_name
            if kind == self._INSERT:
                for r in relations(self._insert_order):
                    table_name = make_table_name(r)
                    table_alias = r.alias or table_name
                    column_names = []
                    column_values = []
                    for c in columns:
                        if c.name is None:
                            continue
                        rel, col = _gsql_column_table_column(c.name)
                        if rel == table_alias and col != 'oid' and c.insert:
                            column_names.append(col)
                            if c.insert == '':
                                val = 'new.%s' % (c.alias)
                            else:    
                                val = c.insert
                                column_values.append(val)
                    bodycolumns = ',\n      '.join(column_names)
                    values = ',\n      '.join(column_values)
                    if len(column_names) > 0:
                        body.append('INSERT INTO %s (\n      %s)\n     '
                                    'VALUES (\n      %s)' % (table_name,
                                                             bodycolumns,
                                                             values))
            elif kind == self._UPDATE:
                for r in relations(self._update_order):
                    table_name = make_table_name(r)
                    if isinstance(r.relation, Select):
                        continue
                    table_alias = r.alias or table_name
                    column_names = []
                    values = []                
                    for c in columns:
                        if c.name is None:
                            continue
                        rel, col = _gsql_column_table_column(c.name)
                        if rel == table_alias and col != 'oid' and c.update:
                            column_names.append(col)
                            if c.update == '':
                                val = 'new.%s' % (c.alias)
                            else:    
                                val = c.update                            
                                values.append(val)
                    settings = ',\n      '.join(['%s = %s' % (c, v)
                                                 for c, v in zip(column_names,
                                                                 values)])
                    if len(column_names) > 0:
                        key_column = get_key_column(r)
                        if not key_column:
                            raise ProgramError("Update rule: no key column "
                                           "specified", table_name)
                        condition = '%s = old.%s' % (key_column, key_column)                        
                        body.append('UPDATE %s SET\n      %s \n    WHERE %s' % 
                                    (table_name, settings, condition))
            elif kind == self._DELETE:
                for r in relations(self._delete_order):
                    table_name = make_table_name(r)
                    if isinstance(r.relation, Select):
                        continue
                    key_column = get_key_column(r)
                    if not key_column:
                        raise ProgramError("Delete rule: no key column "
                                           "specified", table_name)
                    condition = '%s = old.%s' % (key_column, key_column)
                    body.append('DELETE FROM %s \n    WHERE %s' % (table_name,
                                                                   condition,))
            else:
                raise ProgramError('Invalid rule specifier', kind)
            return body
        def get_params(kind):
            if kind == self._INSERT:
                command = 'INSERT'
                suffix = 'ins'
                action = self._insert
            elif kind == self._UPDATE:
                command = 'UPDATE'
                suffix = 'upd'
                action = self._update
            elif kind == self._DELETE:
                command = 'DELETE'
                suffix = 'del'
                action = self._delete
            else:    
                raise ProgramError('Invalid rule specifier', kind)
            return action, command, suffix
        action, command, suffix = get_params(kind)
        if action is None:
            body = 'NOTHING'
        elif is_sequence(action):
            if self._set:
                body = []
            else:    
                body = get_default_body(kind)
            body = list(body) + list(action)
            if len(body) == 0:
                body = 'NOTHING'
            else:
                body = '(%s;)' % (';\n    '.join(body))
        else:
            body = action
        return ('CREATE OR REPLACE RULE %s_%s AS\n ON %s TO %s DO INSTEAD \n' + \
                '    %s;\n\n') % \
               (self._name, suffix, command, self._name, body)
        
    def _output(self, table_keys):
        select = self.format_select()
        result = 'CREATE OR REPLACE VIEW %s AS\n%s;\n\n' % \
                 (self._name, select)        
        for kind in (self._INSERT, self._UPDATE, self._DELETE):
            result = result + self._format_rule(kind, table_keys)
        if self._doc is not None:
            doc = "COMMENT ON VIEW %s IS '%s';\n" % \
                  (self._name, _gsql_escape(self._doc))
            result = result + doc
        result = result + self._revoke_command()
        for g in self._grant:
            result = result + self._grant_command(g)
        return result

    def outputall(self, table_keys):
        return self.output(table_keys)
    
    def reoutput(self, table_keys):
        return self.output(table_keys)

    def convert(self):
        items = ['class %s(sql.SQLView):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name.lower()),))
        self._convert_schemas(items)
        if self._primary_column is not None:
            items.append('    primary_column = %s' % (repr(self._primary_column),))
        definitions = []
        condition = self._convert_select(definitions, 0)
        if definitions and definitions[-1].startswith(condition + ' = '):
            condition = definitions.pop()
            condition = condition[condition.find(' = ')+3:]
        if (condition == 'select_1()' and
            definitions and
            definitions[0] == 'def select_1():' and
            all([d and d[0] == ' ' for d in definitions[1:]])):
            new_definitions = []
            for d in definitions[1:]:
                new_definitions.append(string.join([dd[4:] for dd in d.split('\n')], '\n'))
            definitions = new_definitions
            condition = None
        definition_lines = []
        for d in definitions:
            definition_lines.append(string.join(['        %s\n' % (dd,) for dd in d.split('\n')], ''))
        items.append('    @classmethod\n    def query(cls):\n%s' % (string.join(definition_lines, ''),))
        if condition is not None:
            items[-1] += '        return %s' % (condition,)
        if self._name == 'ev_pytis_menu_structure':
            items.append('    @classmethod\n    def join_columns(class_):\n        return ((sql.c.APytisActionsStructure.fullname, sql.c.CPytisMenuActions.fullname),)')
        def quote(command):
            if '\n' in command:
                command = '""%s""' % (command,)
            return command
        def add_rule(kind, command, order):
            if command is None:
                return
            if isinstance(command, basestring):
                items.append('    def on_%s(self):' % (kind,))
                items.append ('        return ("%s",)' % (quote(command),))
            else:
                def make_table_name(r):
                    table_name = r.relation
                    if isinstance(r, SelectRelation) and r.schema is not None:
                        table_name = '%s.%s' % (r.schema, table_name,)
                    return table_name
                def relations(list_order):
                    if self._set:
                        return ()
                    if list_order is None:
                        rels = self._relations
                    else:
                        rels = []
                        for r in list_order:
                            rel = find(r, self._relations, lambda x: x.relation)
                            if rel is not None and \
                               not isinstance(rel.relation, SelectRelation):
                                rels.append(rel)
                    return rels
                def update_value(c):
                    return c.insert if kind == 'insert' else c.update
                real_order = relations(order)
                real_order_relations = []
                no_update_columns = []
                special_update_columns = []
                for r in real_order:
                    table_name = make_table_name(r)
                    if kind != 'insert' and isinstance(r.relation, Select):
                        continue
                    table_alias = r.alias or table_name
                    if kind == 'delete':
                        real_order_relations.append(make_table_name(r))
                    else:
                        for c in self._columns:
                            if c.name is None:
                                continue
                            rel, col = _gsql_column_table_column(c.name)
                            if rel == table_alias and col != 'oid' and update_value(c):
                                t_name = make_table_name(r)
                                real_order_relations.append(t_name)
                                for cc in self._columns:
                                    cc_alias = cc.alias
                                    u_value = update_value(cc)
                                    if not u_value:
                                        no_update_columns.append(cc_alias)
                                    elif u_value != 'new.%s' % (cc_alias,):
                                        cc_orig_name = cc.name.split('.')[-1]
                                        special_update_columns.append((t_name, cc_orig_name, u_value,))
                                break
                prefix = ''
                for o in real_order_relations:
                    if o.find('.') >= 0:
                        prefix = '#XXX:'
                        break
                order_string = string.join([self._convert_name(o.lower()) for o in real_order_relations], ', ')
                if order_string:
                    order_string += ','
                items.append('%s    %s_order = (%s)' % (prefix, kind, order_string,))
                if no_update_columns:
                    column_string = string.join(["'%s'" % (c,) for c in no_update_columns], ', ') + ','
                    items.append('    no_%s_columns = (%s)' % (kind, column_string,))
                if special_update_columns:
                    column_string = string.join([repr(c) for c in special_update_columns], ', ') + ','
                    items.append('    special_%s_columns = (%s)' % (kind, column_string,))
                command_string = string.join(['"%s"' % (quote(c),) for c in command], ', ')
                if command_string:
                    items.append('    def on_%s_also(self):' % (kind,))
                    items.append ('        return (%s,)' % (command_string,))
        add_rule('insert', self._insert, self._insert_order)
        add_rule('update', self._update, self._update_order)
        add_rule('delete', self._delete, self._delete_order)
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        result = string.join(items, '\n') + '\n'
        return result

ViewNG = _GsqlViewNG    

class _GsqlView(_GsqlSpec):
    """Specifikace view."""
    
    _SQL_NAME = 'VIEW'
    _PGSQL_TYPE = 'v'

    _INSERT = 'INSERT'
    _UPDATE = 'UPDATE'
    _DELETE = 'DELETE'
    
    def __init__(self, name, columns, key_columns=None,
                 table_alias=None, join=None,
                 insert=(), update=(), delete=(), **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno view jako SQL string; může být též instance třídy
            '_GsqlTable', v kterémžto případě je jméno view zkonstruováno ze
            jména tabulky přidáním písmene 'v' před první podtržítko v názvu
            tabulky nebo na jeho konec, pokud žádné podtržítko neobsahuje
          columns -- specifikace sloupců view, sekvence instancí třídy
            'ViewColumn'
          table_alias -- pokud není None, určuje pomocí sekvence
            dvojic (TAB, ALIAS) aliasy k tabulkám, které se ve view používají
          key_columns -- sekvence jmen klíčových sloupců view, tj. sloupců
            jednoznačně identifikujících záznam, strings
          join -- určuje způsob spojení tabulek, je-li view složeno z více
            tabulek.  Je-li 'None', není na spojení tabulek kladena žádná
            podmínka; je-li string, jedná se o SQL string určující podmínku
            spojení tabulek; je-li sekvence dvojic '(COL1, COL2)', každá
            z těchto dvojic určuje relační spojení tabulek prostřednictvím
            daných sloupců, které musí být uvedeny svým názvem včetně tabulky
            jako SQL strings.  Je-li view sjednocením více tabulek, má argument
            stejnou podobu až na to, že je sekvencí výše uvedených specifikací
            (není-li 'None'), v pořadí odpovídajícím pořadí tabulek ve
            specifikaci sloupců.
          insert -- specifikace akce nad view při provedení operace INSERT.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po vložení předaných hodnot sloupců do tabulky
            prvního sloupce view.
          update -- specifikace akce nad view při provedení operace UPDATE.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po updatu předaných hodnot sloupců v tabulce
            prvního sloupce view.
          delete -- specifikace akce nad view při provedení operace DELETE.
            Je-li 'None', je operace blokována, neprovádí se při ní nic.  Je-li
            string, jedná se o SQL string definující kompletní DO INSTEAD akci.
            Je-li sekvencí SQL strings, definují tyto strings SQL příkazy
            provedené navíc po smazání daného záznamu z tabulky prvního sloupce
            view.
          kwargs -- argumenty předané konstruktoru předka

        """
        assert is_sequence(table_alias) or table_alias is None
        if isinstance(name, _GsqlTable):
            table = name
            tname = table.name()
            pos = tname.find('_')
            if pos == -1:
                pos = len(tname)
            name = tname[:pos] + 'v' + tname[pos:]
        super(_GsqlView, self).__init__(name, **kwargs)
        self._columns = columns
        self._table_alias = table_alias
        self._join = join
        self._insert = insert
        self._update = update
        self._delete = delete
        self._key_columns = key_columns
        self._complexp = some(lambda c: is_sequence(c.name)
                              or is_sequence(c.sql),
                              self._columns)
        self._simple_columns, self._complex_columns = \
                              self._split_columns()
        self._complex_len = self._complex_columns_length()
        self._tables_from, self._tables = self._make_tables()

    def _column_table(self, column):
        return _gsql_column_table_column(column.name)[0]

    def _column_column(self, column):
        return _gsql_column_table_column(column.name)[1]

    def _split_columns(self):
        """Rozdělí sloupce na jednoduché a složené (UNION)."""       
        if not self._complexp:
            return self._columns, None
        simple_columns = []
        complex_columns = []
        for c in self._columns:
            if is_sequence(c.name) or is_sequence(c.sql):
                complex_columns.append(c)
            else:
                simple_columns.append(c)
        return simple_columns, complex_columns        


    def _complex_columns_length(self):
        if not self._complexp:
            return None
        complex_len = is_sequence(self._complex_columns[0].name) and \
                      len(self._complex_columns[0].name) or \
                      len(self._complex_columns[0].sql) 
        for c in self._complex_columns[1:]:
            clen = is_sequence(c.name) and len(c.name) or len(c.sql)
            if clen != complex_len:
                raise GensqlError("Non-matching column length", c)
        return complex_len

      
    def _make_tables(self):
        """Vytvoří seznam tabulek pro klauzuli from
           a seznam jmen použitých tabulek."""       
        column_tables = []
        if self._complexp:
            for i in range(self._complex_len):
                icomplex_tables = []
                for c in self._complex_columns:
                    if is_sequence(c.name) and c.name[i]:                    
                        tname = _gsql_column_table_column(c.name[i])[0]
                        if tname and tname not in icomplex_tables:
                            icomplex_tables.append(tname)
                column_tables.append(icomplex_tables)            
        else:
            simple_tables = [self._column_table(t)
                             for t in self._columns
                             if self._column_table(t) is not None]
            for t in simple_tables:
                if not t in column_tables:
                    column_tables.append(t)
        # Now we have the list of used tables
        # and we can check the appropriate use of table aliases            
        if self._table_alias:
            table_alias_tables = [x[0] for x in self._table_alias]
            table_alias_aliases = [x[1] for x in self._table_alias]
            tables_from = []
            tables = []
            if self._complexp:
                for tc in column_tables:
                    caliases = []
                    ctables_from = []
                    ctables = []
                    for t in tc:
                        if t in table_alias_tables:
                            raise ProgramError('Table name instead of alias specified',
                                               t)
                        if t in table_alias_aliases and t not in caliases:
                            caliases.append(t)
                            t = rassoc(t, self._table_alias)
                            ctables_from.append(' '.join(t))
                            ctables.append(t[0])
                        else:
                            ctables_from.append(t)
                            ctables.append(t)
                    tables_from.append(ctables_from)
                    tables.append(ctables)
            else:
                aliases = []
                for t in column_tables:
                    if t in table_alias_tables:
                        raise ProgramError('Table name instead of alias specified',
                                           t)
                    if t in table_alias_aliases and t not in aliases:
                        aliases.append(t)
                        t = rassoc(t, self._table_alias)
                        table_from = ' '.join(t)
                        table = t[0]
                    else:
                        table_from = table = t
                    if table_from not in tables_from:
                        tables_from.append(table_from)
                    if table not in tables:
                        tables.append(table)
        else:
            tables_from = tables = column_tables
        return tables_from, tables

               
    def _format_column(self, column, i=None, type=UNDEFINED):
        if isinstance(column, basestring):
            cname = alias = column
        else:
            if i is None:
                if column.sql:
                    cname = column.sql
                else:    
                    cname = column.name
            else:
                if column.sql:               
                    cname = column.sql[i]
                else:    
                    cname = column.name[i]
            alias = column.alias
        if type is None:
            cname = 'NULL'
        elif isinstance(type, pytis.data.Type):
            cname = 'NULL::%s' % _gsql_format_type(type)
        elif isinstance(type, basestring):
            cname = 'NULL::%s' % type
        return '%s AS %s' % (cname, alias)

    def _format_complex_columns(self):
        COLSEP = ',\n        '
        def format_simple_columns(columns):
            return string.join(map(self._format_column, columns), COLSEP)
        if self._complexp:
            result_base = format_simple_columns(self._simple_columns)
            result = []
            for i in range(self._complex_len):
                colspecs = []
                for c in self._complex_columns:
                    names = c.name
                    if not c.sql and names[i] is None:
                        type = c.type
#                         for j in range(len(names)):
#                             if i != j and names[j] is not None:
#                                 table_name, jcol_name = \
#                                   _gsql_column_table_column(names[j])
#                                 tc = find(names[j],
#                                           _gsql_defs[table_name].columns(),
#                                           key=(lambda c: c.name))
#                                 type = tc.type
#                                 name = jcol_name
#                                 break
                        spec = self._format_column(c, type=type)
                    else:
                        spec = self._format_column(c, i)
                    colspecs.append(spec)
                result_complex = string.join(colspecs, COLSEP)
                if result_base != '':
                    result_base = result_base + COLSEP
                result.append(result_base + result_complex)
        else:
            result = format_simple_columns(self._columns)
        return result

    def _format_rule(self, kind):
        table_columns = {}
        if not self._complexp:
            for t in self._tables:
                table_alias = assoc(t, self._table_alias or ())
                table_alias = table_alias and table_alias[1] or t
                cols = []
                for c in self._columns:
                    if not is_sequence(c.name[0]):
                        tname = self._column_table(c)
                        cname = self._column_column(c)
                        if tname == table_alias and cname != 'oid':
                            cols.append(c)
                table_columns[t] = cols
        if kind is self._INSERT:
            command = 'INSERT'
            suffix = 'ins'
            body = []
            if not self._complexp:
                for t in self._tables:
                    column_names = [self._column_column(c)
                                    for c in table_columns[t]
                                    if c.insert]
                    column_values = [c.insert == '' and
                              'new.%s' % (c.alias) or
                              c.insert                                
                              for c in table_columns[t]
                              if c.insert]                
                    columns = ',\n      '.join(column_names)
                    values = ',\n      '.join(column_values)
                    if column_names:
                        body.append('INSERT INTO %s (\n      %s)\n     VALUES (\n      %s)' % \
                                    (t, columns, values))
            action = self._insert
            body = string.join(body, ';\n    ')
        elif kind is self._UPDATE:
            command = 'UPDATE'
            suffix = 'upd'
            body = []
            if not self._complexp:
                for t in self._tables:
                    column_names = [self._column_column(c)
                                    for c in table_columns[t]
                                    if c.update]                
                    values = [c.update == '' and
                              'new.%s' % (c.alias) or
                              c.update                                
                              for c in table_columns[t]
                              if c.update]                
                    settings = ',\n      '.join(['%s = %s' % (c, v)
                                                 for c, v in zip(column_names,
                                                                 values)])
                    rels = ['%s = old.%s' % (c, _gsql_column_table_column(c)[1])
                            for c in self._key_columns
                            if _gsql_column_table_column(c)[0] == t]
                    condition = string.join(rels, ' AND ')
                    if column_names:
                        body.append('UPDATE %s SET\n      %s \n    WHERE %s' % \
                                    (t, settings, condition))
            action = self._update
            body = string.join(body, ';\n    ')
        elif kind is self._DELETE:
            command = 'DELETE'
            suffix = 'del'
            body = []
            if not self._complexp:
                for t in self._tables:
                    rels = ['%s = old.%s' % (c, _gsql_column_table_column(c)[1])
                            for c in self._key_columns
                            if _gsql_column_table_column(c)[0] == t]
                    condition = string.join(rels, ' AND ')
                    body.append('DELETE FROM %s \n    WHERE %s' % (t, condition))
            action = self._delete
            body = string.join(body, ';\n    ')            
        else:
            raise ProgramError('Invalid rule specifier', kind)
        if action is None:
            body = 'NOTHING'
        elif is_sequence(action):
            body = '(%s;\n    %s)' % (body, string.join(action, ';\n    '))
        else:
            body = action
        return ('CREATE OR REPLACE RULE %s_%s AS\n ON %s TO %s DO INSTEAD \n' + \
                '    %s;\n\n') % \
               (self._name, suffix, command, self._name, body)

    def columns(self):
        return self._columns
        
    def _output(self, table_keys):
        columns = self._format_complex_columns()
        is_union = is_sequence(columns)        
        if self._key_columns is None:
            if is_union:
                tables = functools.reduce(operator.add, self._tables)
            else:
                tables = self._tables
            key_columns = []
            for t in tables:
                if t in table_keys:
                    key_columns = key_columns + table_keys[t]
            self._key_columns = key_columns
        if self._join is None:
            where = ''
        else:
            def gen_where(spec):
                if spec is None:
                    return ''
                where = ' WHERE '
                if isinstance(spec, basestring):
                    join = spec
                else:
                    rels = ['%s = %s' % r for r in spec]
                    join = string.join(rels, ' AND ')
                where = where + join
                return where
            if is_sequence(columns):
                where = map(gen_where, self._join)
            else:
                where = gen_where(self._join)
        if is_union:
            tables = map(lambda t: string.join(t, ', '), self._tables_from)
            selections = [' SELECT\n\t%s\n FROM %s\n%s' % (c, t, w)
                          for t, c, w in zip(tables,
                                             columns, where)]
            body = string.join(selections, ' UNION ALL\n')
        else:
            tables = string.join(self._tables_from, ', ')
            body = ' SELECT\n\t%s\n FROM %s\n%s' % (columns, tables, where)
        result = 'CREATE OR REPLACE VIEW %s AS\n%s;\n\n' % \
                 (self._name, body)
        for kind in (self._INSERT, self._UPDATE, self._DELETE):
            result = result + self._format_rule(kind)
        if self._doc is not None:
            doc = "COMMENT ON VIEW %s IS '%s';\n" % \
                  (self._name, _gsql_escape(self._doc))
            result = result + doc
        result = result + self._revoke_command()
        for g in self._grant:
            result = result + self._grant_command(g)
        return result

    def outputall(self, table_keys):
        return self.output(table_keys)
    
    def reoutput(self, table_keys):
        return self.output(table_keys)

    def _convert_column(self, column, i=None, type=UNDEFINED):
        if isinstance(column, basestring):
            cname = alias = column
        else:
            if i is None:
                if column.sql:
                    cname = column.sql
                else:    
                    cname = column.name
            else:
                if column.sql:               
                    cname = column.sql[i]
                else:    
                    cname = column.name[i]
            alias = column.alias
        if type is None:
            cname = "NULL"
        elif isinstance(type, pytis.data.Type):
            cname = "NULL::%s" % (_gsql_format_type(type),)
        elif isinstance(type, basestring):
            cname = "NULL::%s" % (type,)
        match = re.match('^([a-zA-Z_][a-zA-Z_0-9]*)\.([a-zA-Z_][a-zA-Z_0-9]*) *$', cname)
        if match and match.group(2) != 'oid':
            crepr = '%s.c.%s' % (self._convert_local_name(match.group(1).lower()),
                                 match.group(2).lower(),)
        else:
            crepr = 'sql.gL("%s")' % (self._convert_literal(cname),)
        return '%s.label(%s)' % (crepr, repr(alias.strip()),)

    def _convert_complex_columns(self):
        COLSEP = ',\n        '
        def format_simple_columns(columns):
            return string.join(map(self._convert_column, columns), COLSEP)
        if self._complexp:
            result_base = format_simple_columns(self._simple_columns)
            result = []
            for i in range(self._complex_len):
                colspecs = []
                for c in self._complex_columns:
                    names = c.name
                    if not c.sql and names[i] is None:
                        type = c.type
                        spec = self._convert_column(c, type=type)
                    else:
                        spec = self._convert_column(c, i)
                    colspecs.append(spec)
                result_complex = string.join(colspecs, COLSEP)
                if result_base != '':
                    result_base = result_base + COLSEP
                result.append(result_base + result_complex)
        else:
            result = format_simple_columns(self._columns)
        return result
    
    def convert(self):
        items = ['class %s(sql.SQLView):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name.lower()),))
        self._convert_schemas(items)
        # The hard part
        columns = self._convert_complex_columns()
        is_union = is_sequence(columns)
        if self._key_columns is None:
            if is_union:
                tables = functools.reduce(operator.add, self._tables)
            else:
                tables = self._tables
        if self._join is None:
            where = ''
        else:
            def gen_where(spec):
                if spec is None:
                    return ''
                where = ''
                if isinstance(spec, basestring):
                    join = spec
                else:
                    rels = ['%s = %s' % r for r in spec]
                    join = string.join(rels, ' AND ')
                where = where + join
                return where
            if is_sequence(columns):
                where = map(gen_where, self._join)
            else:
                where = gen_where(self._join)
        items.append('    @classmethod\n    def query(cls):')
        if is_union:
            def transform_table(table):
                t = table.split(' ')
                if len(t) == 1:
                    accessor = "sql.t.%s" % (self._convert_name(t[0], short=True),)
                    alias = t[0]
                elif len(t) == 2:
                    accessor = "sql.t.%s.alias('%s')" % (self._convert_name(t[0], short=True), t[1],)
                    alias = t[-1]
                elif len(t) == 3 and t[1].lower() == 'as':
                    accessor = "sql.t.%s.alias('%s')" % (self._convert_name(t[0], short=True), t[2],)
                    alias = t[2]
                else:
                    raise Exception("Can't decode table name", table)
                alias = self._convert_local_name(alias)
                items.append('        %s = %s' % (alias, accessor,))
                return alias
            tables_from = [[transform_table(t) for t in tt] for tt in self._tables_from]
            tables = [string.join(t, ', ') for t in tables_from]
            selections = []
            for t, c, w in zip(tables, columns, where):
                selections.append('sqlalchemy.select(\n    [\n%s],\n    from_obj=[%s],\n    whereclause=%s)' %
                                  (c, t, repr(w),))
            condition = string.join(selections, '.union_all(')
            condition += ')' * (len(selections) - 1)
        else:
            tables = self._tables_from
            from_obj = []
            for t in tables:
                t = t.lower()
                selector = 'sql.gO'
                pos = t.rfind(' ')
                if pos > 0:
                    name = t[:pos].rstrip()
                    alias = t[pos+1:]
                    if re.match('^([a-zA-Z_][a-zA-Z_0-9]*)\.([a-zA-Z_][a-zA-Z_0-9]*)$', name):
                        selector = 'sql.object_by_name'
                else:
                    name = alias = t
                line = "        %s = %s('%s')" % (self._convert_local_name(alias), selector, name,)
                if name != alias:
                    line += '.alias(%s)' % (repr(alias),)
                items.append(line)
                from_obj.append(alias)
            converted_columns = columns
            in_list = 0
            split_columns = []
            for c in converted_columns.split('\n'):
                if split_columns:
                    indentation = '     ' + ' ' * in_list
                else:
                    indentation = ''
                split_columns.append(indentation + c)
                if c.lstrip().startswith('['):
                    in_list += 1
                if c.rstrip().endswith(']'):
                    in_list -= 1
            columns = string.join(split_columns, '\n')
            condition = ('sqlalchemy.select(\n            [%s],\n            from_obj=[%s],\n            whereclause=%s)' %
                         (columns, string.join(from_obj, ', '), repr(where),))
        items.append('        return %s' % (condition,))
        # Rules
        def quote(command):
            if '\n' in command:
                command = '""%s""' % (command,)
            return command
        def add_rule(kind, command):
            if command is None:
                return
            if isinstance(command, basestring):
                items.append('    def on_%s(self):' % (kind,))
                items.append ('        return ("%s",)' % (quote(command),))
            else:
                prefix = ''
                for t in self._tables:
                    if t.find('.') >= 0:
                        prefix = '#XXX:'
                        break
                if kind == 'delete' or self._complexp:
                    order_tables = self._tables
                else:
                    order_tables = []
                    for t in self._tables:
                        table_alias = assoc(t, self._table_alias or ())
                        table_alias = table_alias and table_alias[1] or t
                        for c in self._columns:
                            if getattr(c, kind):
                                tname = self._column_table(c)
                                cname = self._column_column(c)
                                if tname == table_alias and cname != 'oid':
                                    order_tables.append(t)
                                    break
                order_string = string.join([self._convert_name(o) for o in order_tables], ', ')
                if order_string:
                    order_string += ','
                items.append('%s    %s_order = (%s)' % (prefix, kind, order_string,))
                command_string = string.join(['"%s"' % (quote(c),) for c in command], ', ')
                if command_string:
                    items.append('    def on_%s_also(self):' % (kind,))
                    items.append ('        return (%s,)' % (command_string,))
            def update_value(c):
                return c.insert if kind == 'insert' else c.update
            no_update_columns = []
            special_update_columns = []
            for cc in self._columns:
                cc_alias = cc.alias
                u_value = update_value(cc)
                if not u_value:
                    no_update_columns.append(cc_alias)
                elif u_value != 'new.%s' % (cc_alias,):
                    cc_orig_name = cc.name.split('.')[-1]
                    special_update_columns.append((self._convert_name(self._tables[0]), cc_orig_name, u_value.replace('\n', ' '),))
            if no_update_columns:
                column_string = string.join(["'%s'" % (c,) for c in no_update_columns], ', ') + ','
                items.append('    no_%s_columns = (%s)' % (kind, column_string,))
            if special_update_columns:
                column_string = string.join(['(%s, "%s", "%s")' % c for c in special_update_columns], ', ') + ','
                items.append('    special_%s_columns = (%s)' % (kind, column_string,))
        add_rule('insert', self._insert)
        add_rule('update', self._update)
        add_rule('delete', self._delete)
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        result = string.join(items, '\n') + '\n'
        return result


class _GsqlFunction(_GsqlSpec):
    """Specifikace SQL funkce."""

    _SQL_NAME = 'FUNCTION'
    
    def __init__(self, name, arguments, output_type, body=None, security_definer=False,
                 optimizer_attributes='VOLATILE',
                 use_functions=(), schemas=None, language=None, **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno funkce, SQL string nebo pythonová funkce (v kterémžto
            případě je jméno SQL funkce shodné s jejím)
          arguments -- sekvence argumentů funkce ve správném pořadí;
            každý prvek sekvence je buď instance třídy 'pytis.data.Type',
            SQL string nebo instance třídy ArgumentType
          output_type -- typ návratové hodnoty funkce; instance třídy
            'pytis.data.Type', SQL string, nebo instance třídy ReturnType
            nebo None (počítá-li se se specifikováním návratové hodnoty pomocí
            modifikátoru 'out' v 'arguments')
          use_functions -- sekvence pythonových funkcí, jejichž definice mají
            být přidány před definici funkce samotné
          schemas -- není-li 'None', definuje schémata, ve kterých má být
            funkce vytvořena, jde o sekvenci řetězců obsahujících textové
            definice postgresové search_path určující search_path nastavenou
            při vytváření funkce, funkce je samostatně vytvořena pro každý
            z prvků této sekvence
          body -- definice funkce; může být buď SQL string obsahující tělo
            funkce ve formě SQL příkazů, nebo pythonová funkce s dostupným
            zdrojovým kódem tvořící tělo funkce v jazyce plpython, nebo 'None',
            v kterémžto případě je funkce pythonová a musí být hodnotou
            argumentu 'name'
          security_definer -- if True, add 'SECURITY DEFINER' to function definition
          optimizer_attributes -- specify one of VOLATILE, IMMUTABLE OR STABLE
          kwargs -- argumenty předané konstruktoru předka

        """
        super(_GsqlFunction, self).__init__(name, **kwargs)
        self._ins, self._outs = self._split_arguments(arguments)
        self._output_type = output_type
        self._use_functions = use_functions
        if body is None:
            body = name
        self._body = body
        self._security_definer = security_definer
        self._language = language
        self._optimizer_attributes = optimizer_attributes.strip().upper()
        self._set_schemas(schemas)
        if self._doc is None and not isinstance(body, basestring):
            self._doc = body.__doc__

    def _split_arguments(self, arguments):
        ins = []
        outs = []
        for a in arguments:
            if isinstance(a, ArgumentType):
                if a.out:
                    outs.append(a)
                else:
                    ins.append(a)
            else:
                ins.append(ArgumentType(a))
        return ins, outs        

    def _format_body(self, body):
        if isinstance(body, basestring):
            if self._use_functions:
                raise GensqlError(
                    "Non-empty use-function list for a non-Python function",
                    self._name)
            result = "'%s' LANGUAGE '%s'" % (body, self._language or 'SQL',)
        else:
            def get_source(f):
                try:
                    lines, __ = inspect.getsourcelines(f)
                except IOError:
                    raise GensqlError(
                        "Source code of %s not available in `%s'" %
                        (f, self._name))
                skip = 1
                if f.__doc__ is not None:
                    skip = skip + len(string.split(f.__doc__, '\n'))
                lines = [l for l in lines if l.strip() != '']
                return _gsql_escape(string.join(lines[skip:], ''))
            source_list = map(get_source, tuple(self._use_functions)+(body,))
            # plpython nemá rád prázdné řádky
            source_text = string.join(source_list, '')
            result = "'%s' LANGUAGE plpythonu" % source_text
        return result

    def _format_arguments(self):
        args = []
        for a in self._ins:
            typ = _gsql_format_type(a.typ)
            arg = "in %s %s" % (a.name, typ)
            args.append(arg.replace('  ',' '))
        for a in self._outs:
            typ = _gsql_format_type(a.typ)
            arg = "out %s %s" % (a.name, typ)
            args.append(arg.replace('  ',' '))
        return ', '.join(args)

    def _format_output_type(self):
        if isinstance(self._output_type, ReturnType):            
            output_type = self._output_type.name
            if self._output_type.setof:
                output_type = 'SETOF ' + output_type
        else:
            output_type = _gsql_format_type(self._output_type)
        return output_type    

    def _format_returns(self):
        if self._output_type is None:
            # Output type must be present in OUT arguments
            if len(self._outs) == 0:
                raise GensqlError(
                    "No output type or output arguments  specified for `%s'" %
                    self._name)
            else:
                returns = ''
        elif isinstance(self._output_type, ReturnType):
            if len(self._outs) > 0:
                # We can have both output_type and out arguments,
                # only to specify "SETOF RECORD" type                
                if not (self._output_type.setof and
                        self._output_type.name.upper() == 'RECORD'):
                    raise GensqlError(
                        "For out arguments only 'SETOF RECORD' output type "
                        "can be specified in `%s'" % self._name)
                else:
                    returns = 'RETURNS SETOF RECORD'
            else:    
                output_type = self._output_type.name
                if self._output_type.setof:
                    output_type = 'SETOF ' + output_type
                returns = 'RETURNS ' + output_type
        else:
            if len(self._outs) > 0:
                raise GensqlError(
                    "For out arguments only 'SETOF RECORD' output type "
                    "can be specified in `%s'" % self._name)
            output_type = _gsql_format_type(self._output_type)
            returns = 'RETURNS %s' % output_type
        return returns

    def _format_security(self):
        if self._security_definer:
            return " SECURITY DEFINER"
        else:
            return ""
        
    def _format_optimizer(self):        
        if self._optimizer_attributes in ('VOLATILE', 'IMMUTABLE', 'STABLE'):
            return " %s" % self._optimizer_attributes
        else:
            return ""
    
    def _output(self):
        # input_types = string.join(map(_gsql_format_type, self._input_types),
        #                          ',')
        # output_type = _gsql_format_type(self._output_type)
        arguments = self._format_arguments()
        # output_type = self._format_output_type()
        returns = self._format_returns()
        body = self._format_body(self._body)
        security = self._format_security()
        optimizer = self._format_optimizer()
        result = 'CREATE OR REPLACE FUNCTION %s (%s) %s\nAS %s%s%s;\n' % \
                 (self._name, arguments, returns, body, optimizer, security)
        if self._doc:
        #    doc = "COMMENT ON FUNCTION %s (%s) IS '%s';\n" % \
        #          (self._name, input_types, _gsql_escape(self._doc))
            doc = "COMMENT ON FUNCTION %s (%s) IS '%s';\n" % \
                  (self._name, arguments, _gsql_escape(self._doc))
            result = result + doc
        return result

    def reoutput(self):
        return self.output()

    def db_all_names(self, connection):
        data = connection.query("select proname from pg_proc, pg_namespace where "
                                "pg_proc.pronamespace=pg_namespace.oid and "
                                "pg_namespace.nspname='public'")
        names = []
        for i in range(data.ntuples):
            n = data.getvalue(i, 0)
            if n not in ('plpythonu_call_handler', 'plpgsql_call_handler'):
                names.append(n)
        return names
    db_all_names = classmethod(db_all_names)
    
    def _convert_column(self, column, out=False):
        name = column.name
        ctype = column.typ
        if isinstance(ctype, pytis.data.Type):
            type_ = 'pytis.data.%s()' % (ctype.__class__.__name__,)
        elif isinstance(ctype, _GsqlType):
            type_ = ctype._convert_name()
        elif isinstance(ctype, basestring):
            type_ = self._convert_string_type(ctype)
        else:
            type_ = '#XXX:type:%s' % (ctype,)
        arguments = [repr(name), type_]
        if out:
            arguments.append('out=True')
        return 'sql.Column(%s)' % (string.join(arguments, ', '),)

    def convert(self):
        name = self._name
        body = self._body
        python = not isinstance(body, basestring)
        if python:
            for l in inspect.getsourcelines(body)[0]:
                if l.find('BaseTriggerObject') >= 0:
                    superclass = 'db.Base_PyTriggerFunction'
                    break
            else:
                if self._name in _CONV_PREPROCESSED_NAMES:
                    superclass = 'Base_PyFunction'
                else:
                    superclass = 'db.Base_PyFunction'
        elif self._language == 'plpgsql':
            superclass = 'sql.SQLPlFunction'
        else:
            superclass = 'sql.SQLFunction'
        items = ['class %s(%s):' % (self._convert_name(new=True), superclass,)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        self._convert_schemas(items)
        items.append('    name = %s' % (repr(name),))
        argument_list = ([self._convert_column(a) for a in self._ins] +
                         [self._convert_column(a, out=True) for a in self._outs])
        if argument_list:
            arguments = string.join([argument_list[0] + ','] +
                                    ['                 ' + a + ',' for a in argument_list[1:]],
                                    '\n')
        else:
            arguments = ''
        items.append('    arguments = (%s)' % (arguments,))
        output_type = self._output_type
        if isinstance(output_type, ReturnType):
            multirow = output_type.setof
            output_type = output_type.name
        else:
            multirow = False
        if isinstance(output_type, pytis.data.Type):
            items.append('    result_type = pytis.data.%s()' % (output_type.__class__.__name__,))
        elif isinstance(output_type, basestring):
            type_string = self._convert_string_type(output_type.lower(), allow_none=True)
            if type_string is None:
                self._add_conversion_dependency(output_type, None)
                type_string = self._convert_name(name=output_type)
            items.append('    result_type = %s' % (type_string,))
        elif output_type is None:
            items.append('    #XXX:result_type = None')
        else:
            items.append('    #XXX:result_type = %s' % (output_type,))
        items.append('    multirow = %s' % (multirow,))
        if self._security_definer:
            items.append('    security_definer = True')
        if self._optimizer_attributes:
            items.append('    stability = %s' % (repr(self._optimizer_attributes),))
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        items.append('')
        result = string.join(items, '\n') + '\n'
        if python:
            intro_lines = []
            def get_source(f, main):
                lines, __ = inspect.getsourcelines(f)
                lines = [l.replace('\\\\', '\\') for l in lines if l.strip() != '']
                required_indentation = 4
                skip = 1
                if f.__doc__ is not None:
                    skip = skip + len(string.split(f.__doc__, '\n'))
                if main:
                    match = re.match('( *)def ( *)([^(]*)', lines[0])
                else:
                    body_lines = lines[skip:]
                    match = re.match('( *)[^ ]', body_lines[0])
                indentation = len(match.group(1))
                fill = ' ' * indentation
                long_fill = ' ' * required_indentation + fill
                static_method = fill + '@staticmethod\n'
                ignore_regexp = re.compile('(.* )?(TMoney|TKurz) +=')
                if main:
                    name_pos = match.end(2)
                    lines[0] = lines[0][:name_pos] + name + lines[0][match.end(3):]
                    lines = lines[:skip] + [long_fill + l for l in intro_lines if not ignore_regexp.match(l)] + lines[skip:]
                    lines.insert(0, static_method)
                else:
                    def_regexp = re.compile('def ( *)([^(]*)')
                    while body_lines and not def_regexp.match(body_lines[0][indentation:]):
                        line = body_lines.pop(0)[indentation:]
                        if not ignore_regexp.match(line):
                            intro_lines.append(line)
                    lines = []
                    skip = False
                    for line in body_lines:
                        if ignore_regexp.match(line):
                            continue
                        match = re.match(def_regexp, line[indentation:])
                        if match:
                            sub_pos = indentation + match.end(1)
                            sub_name = match.group(2)
                            if sub_name in ('pg_val', 'pg_escape', 'string', 'boolean', 'num', '_html_table',):
                                skip = True
                            else:
                                skip = False
                                lines.append(static_method)
                                line = line[:sub_pos] + 'sub_' + line[sub_pos:]
                        if skip:
                            continue
                        lines.append(line)
                        if match:
                            for l in intro_lines:
                                lines.append(long_fill + l)
                passed_lines = []
                skip = False
                match_prefix = '    class BaseTriggerObject(object):'
                indentation_prefix = '     '
                for l in lines:
                    if l.startswith(match_prefix):
                        skip = True
                        continue
                    if skip and l.startswith(indentation_prefix):
                        continue
                    skip = False
                    passed_lines.append(l)
                lines = passed_lines
                if indentation < required_indentation:
                    fill = ' ' * (required_indentation - indentation)
                    lines = [fill + l for l in lines]
                elif indentation > required_indentation:
                    cut = indentation - required_indentation
                    lines = [l[cut:] for l in lines]
                return string.join(lines, '') + '\n' if lines else ''
            source_list = ([get_source(f, False) for f in self._use_functions] +
                           [get_source(body, True)])
            result += string.join(source_list, '')
            result += '\n'
        else:
            self._convert_add_raw_dependencies(self._body)
            result += '    def body(self):\n'
            result += '        return """%s"""\n' % (self._body.replace("''", "'"),)
        return result        


class _GsqlSequence(_GsqlSpec):
    """Specifikace sekvence (\"SEQUENCE\")."""

    _SQL_NAME = 'SEQUENCE'
    _PGSQL_TYPE = 'S'
    
    def __init__(self, name, increment=None, minvalue=None,
                 maxvalue=None, start=None, cycle=None, schemas=None, **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- jméno sekvence, SQL string
          increment, minvalue, maxvalue, start, cycle -- viz 'create sequence'
          schemas -- není-li 'None', definuje schémata, ve kterých má být
            databázová sekvence vytvořena, jde o tuple nebo list řetězců
            obsahujících textové definice postgresové search_path určující
            search_path nastavenou při vytváření databázové sekvence, tabulka
            je samostatně vytvořena pro každý z prvků tohoto tuple nebo listu
          kwargs -- argumenty předané konstruktoru předka

        """
        super(_GsqlSequence, self).__init__(name, **kwargs)
        self._increment = increment
        self._minvalue = minvalue
        self._maxvalue = maxvalue
        self._start = start
        self._cycle = cycle
        self._set_schemas(schemas)
        
    def _output(self):
        result = 'CREATE SEQUENCE %s' % self._name
        if self._increment:
            result = result + ' INCREMENT %s' % self._increment
        if self._minvalue:
            result = result + ' MINVALUE %s' % self._minvalue
        if self._maxvalue:
            result = result + ' MAXVALUE %s' % self._maxvalue
        if self._start:
            result = result + ' START %s' % self._start
        if self._cycle:
            result = result + ' CYCLE'
        result = result + ';\n'
        if self._doc is not None:
            doc = "COMMENT ON SEQUENCE %s IS '%s';\n" % \
                  (self._name, _gsql_escape(self._doc))
            result = result + doc
        result = result + self._revoke_command()
        for g in self._grant:
            result = result + self._grant_command(g)
        return result

    def convert(self):
        items = ['class %s(sql.SQLSequence):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name),))
        self._convert_schemas(items)
        if self._start:
            items.append('    start = %s' % (self._start,))
        if self._increment:
            items.append('    increment = %s' % (self._increment,))
        if self._cycle:
            items.append('    #XXX: cycle = %s' % (self._cycle,))
        if self._minvalue:
            items.append('    #XXX: minvalue = %s' % (self._minvalue,))
        if self._maxvalue:
            items.append('    #XXX: maxvalue = %s' % (self._maxvalue,))
        items.append(self._convert_depends())
        items.append(self._convert_grant())
        result = string.join(items, '\n') + '\n'
        return result        


class _GsqlRaw(_GsqlSpec):
    """Prosté SQL příkazy."""
    
    def __init__(self, sql, file_name=None, schemas=None, **kwargs):
        """Inicializuj instanci.

        Argumenty:

          sql -- SQL příkazy, SQL string
          file_name -- byly-li SQL příkazy načteny jako kompletní obsah
            nějakého SQL souboru, je tento argument jménem onoho souboru
            (v jakékoliv podobě, tento argument má pouze funkci dokumentační);
            v jiném případě je 'None'
          schemas -- není-li 'None', definuje schémata, ve kterých mají být
            příkazy provedeny, jde o sekvenci řetězců obsahujících textové
            definice postgresové search_path určující search_path nastavenou
            při provádění příkazů, příkazy jsou samostatně provedeny pro každý
            z prvků této sekvence
          kwargs -- argumenty předané konstruktoru předka

        """
        if 'name' not in kwargs:
            kwargs['name'] = None
        super(_GsqlRaw, self).__init__(**kwargs)
        self._sql = sql
        self._file_name = file_name
        self._set_schemas(schemas)

    def _output(self):
        result = self._sql + '\n'
        if self._file_name:
            result = '''
            
---------------------------
-- Included file: %s --
---------------------------

%s

-- End of included file: %s
''' % (self._file_name, result, self._file_name)
        return result

    def reoutput(self):
        sys.stdout.write(
            _gsql_warning("Raw SQL commands not considered: %s" %
                          self.name()))
        return super(_GsqlRaw, self).reoutput()

    def db_update(self, connection):
        return _gsql_warning('Raw command not considered: %s' % self.name())

    def convert(self):
        items = ['class %s(sql.SQLRaw):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name),))
        self._convert_schemas(items)
        items.append('    @classmethod')
        items.append('    def sql(class_):')
        items.append('        return """%s"""' % (self._sql.replace("\\'", "'").replace('\\', '\\\\'),))
        items.append(self._convert_depends())
        result = string.join(items, '\n') + '\n'
        self._convert_add_raw_dependencies(self._sql)
        return result        


class _GviewsqlRaw(_GsqlSpec):
    """View definované prostými SQL příkazy."""
   
    def __init__(self, name, columns, fromitems, where=None, 
                 groupby=None, having=None,
                 insert=None, update=None, delete=None,
                 **kwargs):
        """Inicializuj instanci.

        Argumenty:

          name -- název view
          columns -- textově vyjmenované sloupce
          fromitems -- textově vyjmenované relace a joins
          where -- textově vyjmenované podmínky
          groupby -- textově vyjmenované GROUP BY
          having -- textově vyjmenované HAVING
          insert -- None nebo textově vyjmenované akce pro insert rule
          update -- None nebo textově vyjmenované akce pro update rule
          delete -- None nebo textově vyjmenované akce pro delete rule
          kwargs -- argumenty předané konstruktoru předka
        """
        super(_GviewsqlRaw, self).__init__(name, **kwargs)
        self._columns = columns
        self._fromitems = fromitems
        self._where = where
        self._groupby = groupby
        self._having = having
        self._insert = insert
        self._update = update
        self._delete = delete

    def _format_rule(self, kind, action):
        suffixes = {'INSERT': 'ins',
                    'UPDATE': 'upd',
                    'DELETE': 'del',
                    }
        if action is None:
            body = 'NOTHING'
        elif is_sequence(action):
            body = '(%s;\n    %s)' % (body, string.join(action, ';\n    '))
        else:
            body = action
        rule = ("CREATE OR REPLACE RULE %s_%s\n"
                "AS ON %s TO %s DO INSTEAD\n"
                "%s;\n\n") % (self._name, suffixes[kind],
                           kind, self._name, body)
        return rule

    def _output(self):
        if isinstance(self._columns, types.TupleType):
            self._columns = ', '.join(self._columns)
        body = "SELECT %s\nFROM %s\n" % (self._columns, self._fromitems)
        if self._where:
            body += "WHERE %s\n" % self._where
        if self._groupby:
            body += "GROUP BY %s\n" % self._groupby
        if self._having:
            body += "HAVING %s\n" % self._having
        result = "CREATE OR REPLACE VIEW %s AS\n%s;\n\n" % \
                 (self._name, body)
        for kind, action in (('INSERT', self._insert),
                             ('UPDATE', self._update),
                             ('DELETE', self._delete)):
            result = result + self._format_rule(kind, action)
        if self._doc is not None:
            result += "COMMENT ON VIEW %s IS '%s';\n" % (self._name, self._doc)
        result = result + self._revoke_command()
        for g in self._grant:
            result = result + self._grant_command(g)
        return result

    def reoutput(self):
        return self._output()

    def db_update(self, connection):
        return _gsql_warning('Raw command not considered: %s' % self.name())

    def convert(self):
        items = ['class %s(sql.SQLRaw):' % (self._convert_name(new=True),)]
        doc = self._convert_doc()
        if doc:
            items.append(self._convert_indent(doc, 4))
        items.append('    name = %s' % (repr(self._name),))
        self._convert_schemas(items)
        sql_string = self._output()
        items.append('    @classmethod')
        items.append('    def sql(class_):')
        items.append('        return """%s"""' % (sql_string.replace('\\', '\\\\'),))
        items.append(self._convert_depends())
        result = string.join(items, '\n') + '\n'
        self._convert_add_raw_dependencies(sql_string)
        return result


class _GsqlDefs(UserDict.UserDict):

    def __init__(self):
        UserDict.UserDict.__init__(self)
        self._resolved = []
        self._unresolved = []
        self._table_keys = {}
        self._relation_columns = {}
        self._specifications = []
        
    def _resolvedp(self, spec):
        missing = some(lambda d: d not in self._resolved, spec.depends())
        return not missing

    def _update_unresolved(self):
        resolved, unresolved = self._resolved, self._unresolved
        while True:
            new_unresolved = []
            for o in unresolved:
                if self._resolvedp(self[o]):
                    self._add_resolved(o)
                else:
                    new_unresolved.append(o)
            if len(unresolved) == len(new_unresolved):
                self._unresolved = unresolved
                break
            else:
                unresolved = new_unresolved

    def _process_resolved(self, function):
        for o in self._unresolved:
            missing = [d for d in self[o].depends() if d not in self._resolved]
            _signal_error('Unresolved object: %s %s\n' % (o, missing,))
        for o in self._resolved:
            function(o)

    def _add_resolved(self, name):
        i = len(self._resolved)
        for o in self._resolved:
            if name in self[o].depends():
                i = self._resolved.index(o)
                break
        self._resolved.insert(i, name)
        # Pro tables a views updatujeme seznam sloupců
        spec = self[name]
        if isinstance(spec, _GsqlTable) or isinstance(spec, _GsqlView):
            self._relation_columns[name] = spec.columns()
        elif isinstance(spec, Select):
            spec.set_columns(self._relation_columns)
            self._relation_columns[name] = spec.columns()
        
    def add(self, spec):
        self._specifications.append(spec)
        name = spec.name()
        if isinstance(spec, _GsqlTable):
            if name not in self._table_keys:
                self._table_keys[name] = spec.key_columns()
            for v in spec._views:
                vname = v.name()
                self[vname] = v
                if self._resolvedp(v):
                    self._add_resolved(vname)
                    self._update_unresolved()
                else:
                    self._unresolved.append(vname)
        if name in self:
            _signal_error("Duplicate objects for name `%s': %s %s\n" %
                          (name, spec, self[name],))
        self[name] = spec
        if self._resolvedp(spec):
            self._add_resolved(name)
            self._update_unresolved()
        else:
            self._unresolved.append(name)

    def gensql(self):
        # Add some dependencies
        def process(o):
            self[o].convert()
        self._process_resolved(process)
        # Make new processor
        defs = self.__class__()
        for s in self._specifications:
            defs.add(s)
        # And make the real conversion
        defs._gensql()

    def _gensql(self):
        def process(o):
            if isinstance(self[o], (_GsqlView, _GsqlViewNG)):
                sys.stdout.write(self[o].output(self._table_keys))
            else:
                sys.stdout.write(self[o].output())
            sys.stdout.write('\n')
        self._process_resolved(process)

    def gensqlall(self):
        def process(o):
            if isinstance(self[o], (_GsqlView, _GsqlViewNG)):
                sys.stdout.write(self[o].outputall(self._table_keys))
            else:
                sys.stdout.write(self[o].outputall())
            sys.stdout.write('\n')
        self._process_resolved(process)

    def regensql(self):
        def process(o):
            if isinstance(self[o], (_GsqlView, _GsqlViewNG)):
                sys.stdout.write(self[o].reoutput(self._table_keys))
            else:
                sys.stdout.write(self[o].reoutput())
            sys.stdout.write('\n')
        self._process_resolved(process)

    def get_connection(self):
        from pyPgSQL import libpq
        while True:
            connection_string = ''
            for option, accessor in (('user', _GsqlConfig.dbuser),
                                     ('password', _GsqlConfig.dbpassword),
                                     ('host', _GsqlConfig.dbhost),
                                     ('port', _GsqlConfig.dbport),
                                     ('dbname', _GsqlConfig.dbname)):
                value = accessor
                if value != None:
                    connection_string = "%s %s='%s'" % \
                                        (connection_string, option, value)
            try:
                connection = libpq.PQconnectdb(connection_string)
            except libpq.DatabaseError as e:
                if string.find(e.args[0], 'password') >= 0:
                    import getpass
                    stdout = sys.stdout
                    sys.stdout = sys.stderr
                    try:
                        _GsqlConfig.dbpassword = getpass.getpass()
                    finally:
                        sys.stdout = stdout
                    continue
                raise
            break
        return connection

    def check_db(self, _quietly=False):
        # Open the database connection
        connection = self.get_connection()
        # Found all relevant objects in all the object classes
        all_names = []
        names = {}
        sql_types_classes = {}
        classes = []
        def process(name):
            o = self[name]
            c = o.__class__
            if c not in classes:
                sql_type = c._SQL_NAME
                classes.append(c)
                sql_types_classes[sql_type] = c
                if sql_type not in names:
                    db_names = c.db_all_names(connection)
                    names[sql_type] = db_names
                    for d in db_names:
                        if d not in all_names:
                            all_names.append(d)
        self._process_resolved(process)
        # Remove objects of wrong types and build the list of objects to update
        to_create = []
        to_update = []
        to_remove = []
        def process(name):
            o = self[name]
            i = position(name, all_names)
            if i is None:
                to_create.append(o)
            else:
                del all_names[i]
                c = o.__class__
                sql_type = c._SQL_NAME
                if name in names[sql_type]:
                    to_update.append(o)
                    names[sql_type].remove(name)
                else:
                    to_remove.append(o)
                for n in o.extra_names():
                    try:
                        all_names.remove(n)
                    except ValueError:
                        pass
        self._process_resolved(process)
        for o in to_remove:
            sys.stdout.write(o.db_remove(o.name()))
        # Remove orphans
        for sql_type, ns in names.items():
            c = sql_types_classes[sql_type]
            for n in ns:
                if n in all_names:
                    if _GsqlConfig.check_presence:
                        sys.stdout.write('EXTRA: %s\n' % (n,))
                    else:
                        sys.stdout.write(c.db_remove(n))
        # Create and update objects
        for o in to_create:
            if _GsqlConfig.check_presence:
                sys.stdout.write('MISSING: %s\n' % (o.name(),))
            elif isinstance(o, (_GsqlView, _GsqlViewNG)):
                sys.stdout.write(o.output(self._table_keys))
            else:
                sys.stdout.write(o.output())
        for o in to_update:
            update_commands = o.db_update(connection)
            if _GsqlConfig.check_presence:
                for line in update_commands.split('\n'):
                    if line and line[:2] != '--':
                        sys.stdout.write('CHANGED: %s\n' % (o.name(),))
                        break
            else:
                sys.stdout.write(update_commands)
        # Finish
        if _GsqlConfig.warnings and not _quietly:
            sys.stderr.write("""
Done.
Objects other than tables and sequences not checked.  You can use the
--recreate option to replace them unconditionally, without any loss of data.
References, triggers and special constraints not checked -- there are no easy
introspection means to check them.
Other checks may be missing as well.  Please create a new database and compare
database dumps if you want to be sure about your schema.
""")

    def fix_db(self):
        self.check_db(_quietly=True)
        self.regensql()

    def update_views(self):
        connection = self.get_connection()
        depends = []
        todo = [_GsqlConfig.update_views]
        while todo != []:
            v = todo.pop()
            if v in depends:
                continue
            else:
                depends.append(v)
            data = connection.query(
               ("select distinct c.relname "
                " from pg_class d, pg_depend a join pg_rewrite b on a.objid=b.oid "
                " join pg_class c on ev_class=c.oid "
                " join pg_views e on e.viewname=c.relname "
                " where refclassid = 'pg_class'::regclass and refobjid = d.oid "
                " and ev_class<>d.oid and d.relname='%s'") %
               v)
            for i in range(data.ntuples):
                todo.append(data.getvalue(i, 0))
        # sys.stdout.write('drop view %s cascade;\n' % obj)        
        def process(o):
            name = self[o].name()
            if name not in depends:
                return
            if isinstance(self[o], (_GsqlView, _GsqlViewNG)):
                sys.stdout.write("DROP VIEW IF EXISTS %s CASCADE;\n\n" % name)
                sys.stdout.write(self[o].reoutput(self._table_keys))
            else:
                sys.stdout.write(self[o].reoutput())
            sys.stdout.write('\n')
        self._process_resolved(process)

    def convert(self):
        # Add some dependencies
        def process(o):
            self[o].convert()
        self._process_resolved(process)
        # Make new processor
        defs = self.__class__()
        for s in self._specifications:
            defs.add(s)
        # And make the real conversion
        defs._convert()

    def _convert(self):
        customization_file = 'convert.py'
        if os.path.exists(customization_file):
            execfile(customization_file, globals())
        application = _GsqlConfig.application
        coding_header = '# -*- coding: utf-8\n'
        local_preamble = '''
from __future__ import unicode_literals

import sqlalchemy
import pytis.data
import pytis.data.gensqlalchemy as sql
'''
        init_preamble = local_preamble
        local_preamble += 'import dbdefs as db\n\n'
        if application:
            if _GsqlConfig.convert_schemas:
                init_preamble += '\n'
                for name, s_tuple in _GsqlConfig.convert_schemas:
                    converted_s_tuple = tuple([tuple(string.split(s, ',')) for s in s_tuple])
                    init_preamble += '%s = %s\n' % (name, repr(converted_s_tuple),)
            if application == 'pytis':
                init_preamble += """
from db_pytis_base import *

"""
            else:
                init_preamble += """
app_default_access_rights = (('all', '%s',),)
app_pytis_schemas = %s
app_cms_rights = (('all', '%s',),)
app_cms_rights_rw = (('all', '%s',),)
app_cms_users_table = '%s'
app_cms_schemas = %s
app_http_attachment_storage_rights = (('insert', '%s'), ('delete', '%s'), ('select', '%swebuser'),)

import imp
import os
import sys
_file, _pathname, _description = imp.find_module('pytis')
sys.path.append(os.path.join(_pathname, 'db', 'dbdefs'))
""" % (application, repr(_GsqlConfig.convert_pytis_schemas),
       application, application, _GsqlConfig.convert_cms_users_table,
       repr(_GsqlConfig.convert_cms_schemas), application, application, application,)
                init_preamble += """
sql.clear()

for m in list(sys.modules.keys()):
    if m.startswith('dbdefs.db_pytis_'):
        del sys.modules[m]
"""
                init_preamble += '\nfrom db_pytis_base import *\n'
        preamble_1 = """
default_access_rights = sql.SQLFlexibleValue('db.app_default_access_rights',
                                               environment='GSQL_DEFAULT_ACCESS_RIGHTS',
                                               default=(('all', '%s',),))
pytis_schemas = sql.SQLFlexibleValue('db.app_pytis_schemas',
                                       environment='GSQL_PYTIS_SCHEMAS',
                                       default=(('public',),))
cms_rights = sql.SQLFlexibleValue('db.app_cms_rights',
                                    environment='GSQL_CMS_RIGHTS',
                                    default=(('all', '%s',),))
cms_rights_rw = sql.SQLFlexibleValue('db.app_cms_rights_rw',
                                       environment='GSQL_CMS_RIGHTS_RW',
                                       default=(('all', '%s',),))
cms_users_table = sql.SQLFlexibleValue('db.app_cms_users_table',
                                         default='cms_users_table')
cms_schemas = sql.SQLFlexibleValue('db.app_cms_schemas',
                                     environment='GSQL_CMS_SCHEMAS',
                                     default=(('public',),))
http_attachment_storage_rights = sql.SQLFlexibleValue('db.app_http_attachment_storage_rights',
                                                        environment='GSQL_HTTP_ATTACHMENT_STORAGE_RIGHTS',
                                                        default=(('insert', '%s'), ('delete', '%s'), ('select', '%swebuser'),))

""" % (application, application, application, application, application, application,)
        preamble_1 += '''
TMoney    = \'numeric(15,2)\'
TKurz     = \'numeric(12,6)\'

class Base_PyFunction(sql.SQLPyFunction):
    @staticmethod
    def sub_pg_escape(val):
        return str(val).replace("\'", "\'\'")
    @staticmethod
    def sub_boolean(val):
        if val is None:
            return "NULL"
        return val and "TRUE" or "FALSE"
    @staticmethod
    def sub_string(val):
        return val is not None and "\'%s\'" % (pg_escape(val)) or "NULL"
    @staticmethod
    def sub_num(val):
        return val is not None and "%s" % (val) or "NULL"
    @staticmethod
    def sub_pg_val(val):
        if val is None:
            pg_value = "NULL"
        elif isinstance(val, (float, int)):
            pg_value = "%s" % (val)
        elif isinstance(val, bool):
            pg_value = val and "TRUE" or "FALSE"
        else:
            pg_value = "\'%s\'" % (pg_escape(val))
        return pg_value
    @staticmethod
    def sub__html_table(columns_labels,rows):
        def st(val):
            if val is None or str(val).strip() == \'\':
                return \'&nbsp;\'
            return str(val).replace(\' \',\'&nbsp;\')
        html_rows=[]
        if len(columns_labels) == 0:
            return None
        html_rows.append(\'<table>\\n<tr>\')
        [html_rows.append(\'<td><b>\'+st(x[1])+\'</b></td>\') for x in columns_labels]
        html_rows.append(\'</tr>\')                         
        for row in rows:
            html_rows.append(\'<tr>\')
            [html_rows.append(\'<td>\'+st(row[x[0]])+\'</td>\') \
             for x in columns_labels]
            html_rows.append(\'</tr>\')
        html_rows.append(\'</table>\')
        html_table = \'\\n\'.join(html_rows)
        return html_table.replace("\'", "\'\'")

class Base_PyTriggerFunction(Base_PyFunction):
    class Sub_BaseTriggerObject(object):
        _RETURN_CODE_MODIFY = "MODIFY"
        _RETURN_CODE_SKIP = "SKIP"
        _RETURN_CODE_OK = None
        def __init__(self, TD):
            self._TD = TD
            self._event = TD["event"].lower()
            self._when = TD["when"].lower()
            self._level = TD["level"].lower() 
            self._name = TD["name"].lower()
            self._table_name = TD["table_name"].lower()
            self._table_schema = TD["table_schema"].lower()
            self._table_oid = TD["relid"]
            self._args = TD["args"]
            # 
            self._new = self._old = None
            if self._event in (\'insert\', \'update\'):
                self._new = TD["new"]
            if self._event in (\'delete\', \'update\'):
                self._old = TD["old"]
            #
            self._return_code = self._RETURN_CODE_OK    
        def _do_after_insert(self):
            pass
        def _do_after_update(self):
            pass
        def _do_after_delete(self):
            pass
        def _do_before_insert(self):
            pass
        def _do_before_update(self):
            pass
        def _do_before_delete(self):
            pass        
        def do_trigger(self):
            if self._when == \'before\':
                if self._event == \'insert\':
                    self._do_before_insert()
                elif self._event == \'update\':
                    self._do_before_update()                    
                elif self._event == \'delete\':
                    self._do_before_delete()
            elif self._when == \'after\':
                if self._event == \'insert\':
                    self._do_after_insert()
                elif self._event == \'update\':
                    self._do_after_update()                    
                elif self._event == \'delete\':
                    self._do_after_delete()
            return self._return_code


'''
        preamble_2 = '''
class Base_LogTrigger(sql.SQLTrigger):
    name = \'log\'
    events = (\'insert\', \'update\', \'delete\',)
    body = LogTrigger

class Base_LogSQLTable(sql.SQLTable):
    @property
    def triggers(self):
        keys = \',\'.join([f.id() for f in self.fields if f.primary_key()])
        return ((Base_LogTrigger, keys,),)

'''
        preamble_x = ['']
        def preprocess(o):
            dbobj = self[o]
            if dbobj.name() in _CONV_PREPROCESSED_NAMES:
                preamble_x[0] += dbobj.convert()
        self._process_resolved(preprocess)
        directory = _GsqlConfig.directory
        visited_files = {}
        if directory is None:
            sys.stdout.write(coding_header)
            index_file = None
        else:
            index_file = os.path.join(directory, '__init__.py')
            visited_files[index_file] = None
            f = open(index_file, 'w')
            f.write(coding_header)
            f.write(init_preamble)
            if application == 'pytis':
                ff = open(os.path.join(directory, 'db_pytis_base.py'), 'w')
                ff.write(coding_header)
                ff.write(local_preamble)
                ff.write(preamble_1)
                ff.write(preamble_x[0])
                ff.write(preamble_2)
                ff.close()
            f.close()
        last_visited_file = [None]
        last_visited_suffix = ['']
        def process(o):
            local_file = True
            dbobj = self[o]
            if dbobj.name() in _CONV_PREPROCESSED_NAMES:
                return
            if directory is None:
                output = sys.stdout
            else:
                basename = os.path.basename(dbobj._gensql_file)
                basename = os.path.splitext(basename)[0]
                if application == 'pytis':
                    if not basename.startswith('db_pytis_'):
                        basename = 'db_pytis_' + basename[3:]
                elif application:
                    if basename in ('db_common', 'db_output', 'db_statistics',):
                        basename = 'db_pytis_' + basename[3:]
                file_name = os.path.join(directory, basename)
                if file_name + '.py' == index_file:
                    new_file = False
                else:
                    new_file = file_name not in visited_files
                    if file_name == last_visited_file[0]:
                        suffix = last_visited_suffix[0]
                    else:                        
                        index = visited_files.get(file_name, 0)
                        visited_files[file_name] = index + 1
                        last_visited_file[0] = file_name
                        if index:
                            suffix = '_' + str(index)
                        else:
                            suffix = ''
                        last_visited_suffix[0] = suffix
                        new_file = True
                    file_name += suffix
                    basename += suffix
                file_name += '.py'
                if application and application != 'pytis' and basename.startswith('db_pytis_'):
                    local_file = False
                if new_file:
                    if (application and
                        not re.match('db_pytis_cms_[3-9]', basename) and
                        # solas hack
                        (basename != 'db_pytis_cms_1' or application != 'solas')):
                        f = open(index_file, 'a')
                        import_name = os.path.splitext(basename)[0]
                        # solas hack
                        if import_name == 'db_sluzby_5':
                            f.write("from db_pytis_cms_1 import *\n")
                        f.write("from %s import *\n" % (import_name,))
                        f.close()
                    if local_file:
                        output = open(file_name, 'w')
                        output.write(coding_header)
                        output.write(local_preamble)
                        global _convert_local_names
                        _convert_local_names = []
                else:
                    if local_file:
                        output = open(file_name, 'a')
            converted = dbobj.convert()
            if not dbobj._convert:
                converted = string.join(['#'+line for line in ['XXX:'] + string.split(converted, '\n')], '\n')
            converted = converted.replace('_RETURN_CODE_MODYFY', '_RETURN_CODE_MODIFY')
            if local_file:
                output.write(converted)
                output.write('\n')
        self._process_resolved(process)
        if application != 'pytis' and index_file is not None:
            f = open(index_file, 'a')
            f.write('\ndel sys.path[-1]\n')
            f.close()


_gsql_defs = _GsqlDefs()

def _gsql_process(class_, args, kwargs):
    spec = class_(*args, **kwargs)
    _gsql_defs.add(spec)
    return spec

def sqltype(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlType."""
    return _gsql_process(_GsqlType, args, kwargs)

def schema(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlSchema."""
    return _gsql_process(_GsqlSchema, args, kwargs)

def table(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlTable."""
    return _gsql_process(_GsqlTable, args, kwargs)

def view(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlView."""
    return _gsql_process(_GsqlView, args, kwargs)

def viewng(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlViewNG."""
    return _gsql_process(_GsqlViewNG, args, kwargs)


def function(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlFunction.
    """
    return _gsql_process(_GsqlFunction, args, kwargs)

def sequence(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GsqlSequence.
    """
    return _gsql_process(_GsqlSequence, args, kwargs)


def sql_raw(text, name=None, depends=(), **kwargs):
    """Specifikace prostých SQL příkazů.

    Argumenty:

      text -- string obsahující kýžené SQL příkazy
      depends -- stejné jako v '_GsqlSpec.__init__()'

    Tato funkce by měla být používána jen ve výjimečných případech, neboť v ní
    obsažený kód je mimo dosah všech kontrol.
      
    """
    kwargs = copy.copy(kwargs)
    kwargs.update({'name': name, 'depends': depends})
    return _gsql_process(_GsqlRaw, (text,), kwargs)


def view_sql_raw(*args, **kwargs):
    """Z hlediska specifikace ekvivalentní volání konstruktoru '_GviewsqlRaw."""
    return _gsql_process(_GviewsqlRaw, args, kwargs)


def sql_raw_include(file_name, depends=(), **kwargs):
    """Specifikace souboru obsahujícího SQL příkazy, který má být načten.

    Tento soubor je beze změny zahrnut do výsledných SQL příkazů.

    Argumenty:

      file_name -- jméno kýženého SQL souboru; absolutní nebo relativní vůči
        aktuálnímu adresáři
      depends -- stejné jako v '_GsqlSpec.__init__()'

    """
    f = open(file_name)
    sql = f.read()
    f.close()
    kwargs = copy.copy(kwargs)
    kwargs.update({'depends': depends, 'file_name': file_name})
    return _gsql_process(_GsqlRaw, (sql,), kwargs)


def include(file_name, globals_=None):
    """Zpracuj pythonový soubor 'file_name'.

    Soubor je zpracován prostřednictvím volání 'execfile()'.
    
    Argumenty:

      file_name -- jméno kýženého pythonového souboru; absolutní nebo relativní
        vůči aktuálnímu adresáři

    """
    global gensql_file
    orig_gensql_file = gensql_file
    gensql_file = file_name
    if globals_ is None:
        globals_ = copy.copy(globals())
    execfile(file_name, globals_)
    gensql_file = orig_gensql_file


###############################################################################


class _GsqlConfig:
    
    GENDB = _gsql_defs.gensql
    GEALL = _gsql_defs.gensqlall
    RGNDB = _gsql_defs.regensql
    CHKDB = _gsql_defs.check_db
    CONVE = _gsql_defs.convert
    FIXDB = _gsql_defs.fix_db
    UPDVW = _gsql_defs.update_views

    request = RGNDB
    warnings = True
    dbname = None
    dbhost = None
    dbport = None
    dbuser = None
    dbpassword = None
    check_presence = False
    directory = None
    application = None
    convert_schemas = ()
    convert_pytis_schemas = (('public',),)
    convert_cms_schemas = (('public',),)
    convert_cms_users_table = 'e_system_user'
    

_GSQL_OPTIONS = (
    ('help             ', 'print this help message and exit'),
    ('create           ', 'create all database objects without data (default action)'),
    ('create-all       ', 'create all database objects with data'),
    ('recreate         ', 'recreate all non-data database objects'),
    ('check-db=DATABASE', 'check DATABASE contents against definitions'),
    ('check-presence   ', 'just check for presence rather than generating updates'),
    ('convert          ', 'convert to gensqlalchemy specifications'),
    ('application=APP  ', 'lowercase name of the converted application'),
    ('update-views=object', 'update views dependent on specified object (table or view)'),
    ('fix-db=DATABASE  ', 'update DATABASE contents according to definitions'),
    ('no-warn          ', 'suppress warnings when checking/fixing'),
    ('host=HOST        ', 'connect to DATABASE at HOST'),
    ('port=PORT        ', 'connect to DATABASE via PORT'),
    ('user=USER        ', 'connect to DATABASE as USER'),
    ('password=PASSWORD', 'use PASSWORD when connecting to DATABASE'),
    ('database=DATABASE', 'DATABASE for connection string'),
    )

def _usage(optexception=None):
    _USAGE = 'usage: %s file\n' % sys.argv[0]
    if optexception:
        sys.stderr.write(optexception.msg)
        sys.stderr.write('\n')
    sys.stderr.write(_USAGE)
    sys.stderr.write('\nOptions:\n')
    for option, description in _GSQL_OPTIONS:
        sys.stderr.write('  --%s %s\n' % (option, description))
    sys.stderr.write('\n')
    sys.exit(_EXIT_USAGE)


def _go(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    def extract_option(odef):
        option = odef[0]
        option = string.strip(option)
        pos = option.find('=')
        if pos >= 0:
            option = option[:pos+1]
        return option
    try:
        opts, args = getopt.getopt(argv, '',
                                   map(extract_option, _GSQL_OPTIONS))
    except getopt.GetoptError as e:
        _usage(e)
    for o, v in opts:
        if o == '--help':
            _usage()
        elif o == '--host':
            _GsqlConfig.dbhost = v
        elif o == '--port':
            _GsqlConfig.dbport = v
        elif o == '--user':
            _GsqlConfig.dbuser = v
        elif o == '--password':
            _GsqlConfig.dbpassword = v
        elif o == '--database':
            _GsqlConfig.dbname = v
        elif o == '--create':
            _GsqlConfig.request = _GsqlConfig.GENDB
        elif o == '--create-all':
            _GsqlConfig.request = _GsqlConfig.GEALL
        elif o == '--recreate':
            _GsqlConfig.request = _GsqlConfig.RGNDB
        elif o == '--check-db':
            _GsqlConfig.request = _GsqlConfig.CHKDB
            _GsqlConfig.dbname = v
        elif o == '--check-presence':
            _GsqlConfig.check_presence = True
        elif o == '--convert':
            _GsqlConfig.request = _GsqlConfig.CONVE
        elif o == '--application':
            _GsqlConfig.application = v
        elif o == '--update-views':
            _GsqlConfig.request = _GsqlConfig.UPDVW
            _GsqlConfig.update_views = v
        elif o == '--fix-db':
            _GsqlConfig.request = _GsqlConfig.FIXDB
            _GsqlConfig.dbname = v
        elif o == '--no-warn':
            _GsqlConfig.warnings = False
        else:
            raise ProgramError('Unrecognized option', o)
    if len(args) == 2 and _GsqlConfig.request is _GsqlConfig.CONVE:
        _GsqlConfig.directory = args[1]
    elif len(args) != 1:
        _usage()
    global gensql_file
    gensql_file = args[0]
    execfile(gensql_file, copy.copy(globals()))
    _GsqlConfig.request()
    

if __name__ == '__main__':
    _go()
    sys.exit(exit_code)
