# -*- coding: utf-8

from __future__ import unicode_literals

import sqlalchemy
import pytis.data.gensqlalchemy as sql
import pytis.data

default_access_rights = sql.SQLFlexibleValue('app_default_access_rights',
                                               environment='GSQL_DEFAULT_ACCESS_RIGHTS',
                                               default=(('all', 'pytis',),))
pytis_schemas = sql.SQLFlexibleValue('app_pytis_schemas',
                                       environment='GSQL_PYTIS_SCHEMAS',
                                       default=(('public',),))
cms_rights = sql.SQLFlexibleValue('app_cms_rights',
                                    environment='GSQL_CMS_RIGHTS',
                                    default=(('all', 'pytis',),))
cms_rights_rw = sql.SQLFlexibleValue('app_cms_rights_rw',
                                       environment='GSQL_CMS_RIGHTS_RW',
                                       default=(('all', 'pytis',),))
cms_users_table = sql.SQLFlexibleValue('app_cms_users_table',
                                         default='cms_users_table')
cms_schemas = sql.SQLFlexibleValue('app_cms_schemas',
                                     environment='GSQL_CMS_SCHEMAS',
                                     default=(('public',),))
http_attachment_storage_rights = sql.SQLFlexibleValue('app_http_attachment_storage_rights',
                                                        environment='GSQL_HTTP_ATTACHMENT_STORAGE_RIGHTS',
                                                        default=(('insert', 'pytis'), ('delete', 'pytis'), ('select', 'pytiswebuser'),))


TMoney    = 'numeric(15,2)'
TKurz     = 'numeric(12,6)'

class Base_PyFunction(sql.SQLPyFunction):
    @staticmethod
    def sub_pg_escape(val):
        return str(val).replace("'", "''")
    @staticmethod
    def sub_boolean(val):
        if val is None:
            return "NULL"
        return val and "TRUE" or "FALSE"
    @staticmethod
    def sub_string(val):
        return val is not None and "'%s'" % (pg_escape(val)) or "NULL"
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
            pg_value = "'%s'" % (pg_escape(val))
        return pg_value
    @staticmethod
    def sub__html_table(columns_labels,rows):
        def st(val):
            if val is None or str(val).strip() == '':
                return '&nbsp;'
            return str(val).replace(' ','&nbsp;')
        html_rows=[]
        if len(columns_labels) == 0:
            return None
        html_rows.append('<table>\n<tr>')
        [html_rows.append('<td><b>'+st(x[1])+'</b></td>') for x in columns_labels]
        html_rows.append('</tr>')                         
        for row in rows:
            html_rows.append('<tr>')
            [html_rows.append('<td>'+st(row[x[0]])+'</td>')              for x in columns_labels]
            html_rows.append('</tr>')
        html_rows.append('</table>')
        html_table = '\n'.join(html_rows)
        return html_table.replace("'", "''")

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
            if self._event in ('insert', 'update'):
                self._new = TD["new"]
            if self._event in ('delete', 'update'):
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
            if self._when == 'before':
                if self._event == 'insert':
                    self._do_before_insert()
                elif self._event == 'update':
                    self._do_before_update()                    
                elif self._event == 'delete':
                    self._do_before_delete()
            elif self._when == 'after':
                if self._event == 'insert':
                    self._do_after_insert()
                elif self._event == 'update':
                    self._do_after_update()                    
                elif self._event == 'delete':
                    self._do_after_delete()
            return self._return_code


class XInserts(sql.SQLTable):
    """Tabulka zaznamenávající přidávání záznamů standardních
    tabulek."""
    name = '_inserts'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(), doc="identifikace řádku"),
              sql.Column('vytvoril', pytis.data.Name(not_null=True), default=sqlalchemy.text('user')),
              sql.Column('vytvoreno', pytis.data.DateTime(not_null=True), default=sqlalchemy.text('now()')),
              sql.Column('tabulka', pytis.data.String(not_null=False)),
              sql.Column('klic', pytis.data.String(not_null=False)),
             )
    with_oids = True
    depends_on = ()
    access_rights = default_access_rights.value(globals())
class XUpdates(sql.SQLTable):
    """Tabulka zaznamenávající změny v záznamech standardních
    tabulek."""
    name = '_updates'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(), doc="identifikace změnového řádku"),
              sql.Column('zmenil', pytis.data.Name(not_null=True), default=sqlalchemy.text('user')),
              sql.Column('zmeneno', pytis.data.DateTime(not_null=True), default=sqlalchemy.text('now()')),
              sql.Column('tabulka', pytis.data.String(not_null=False)),
              sql.Column('klic', pytis.data.String(not_null=False)),
              sql.Column('zmeny', pytis.data.String(not_null=False)),
             )
    with_oids = True
    depends_on = ()
    access_rights = default_access_rights.value(globals())
class XDeletes(sql.SQLTable):
    """Tabulka zaznamenávající vymazávání záznamů ve standardních
    tabulkách."""
    name = '_deletes'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(), doc="identifikace řádku"),
              sql.Column('smazal', pytis.data.Name(not_null=True), default=sqlalchemy.text('user')),
              sql.Column('smazano', pytis.data.DateTime(not_null=True), default=sqlalchemy.text('now()')),
              sql.Column('tabulka', pytis.data.String(not_null=False)),
              sql.Column('klic', pytis.data.String(not_null=False)),
             )
    with_oids = True
    depends_on = ()
    access_rights = default_access_rights.value(globals())
class XLogUpdateTrigger(Base_PyFunction):
    """Slouží k evidenci editací nad záznamy tabulek."""
    name = '_log_update_trigger'
    arguments = ()
    result_type = sql.G_CONVERT_THIS_FUNCTION_TO_TRIGGER
    multirow = False
    stability = 'VOLATILE'
    depends_on = (XInserts, XDeletes, XUpdates,)
    access_rights = ()

    @staticmethod
    def _log_update_trigger():
        def pg_escape(val):
            return val.replace("'", "''").replace(chr(92),2*chr(92))
        event = TD["event"]
        if event == "DELETE":
            newold = "old"
            table = "_deletes"
        elif event == "INSERT":
            newold = "new"
            table = "_inserts"
        else:
            newold = "new"
            table = "_updates"
        tabid = TD["relid"]
        q = "select relname from pg_class where oid = %s" % tabid
        q = plpy.execute(q)
        tabulka = q[0]["relname"]
        klice = TD["args"][0].split(',')
        klicestr = ','.join(["%s: %s" % (k, str(TD[newold][k]))
                             for k in klice])
        # pro INSERT a DELETE zaznamenáme tabulku a klíč
        if event in ("DELETE", "INSERT"):
            q = """insert into %s (tabulka, klic)
                   select '%s', '%s'
                """ % (table, tabulka, klicestr)
            q = plpy.execute(q)
            return None
        # Pro UPDATE zaznamenáme kromě jména tabulky a klíče i změny v položkách
        zmeny = []
        # Zjistime bytea sloupce
        q = """select a.attname
                 from pg_class r, pg_namespace nsp, pg_attribute a, pg_type t
                where r.relname = '%s' and r.relnamespace = nsp.oid and nsp.nspname = '%s'
                  and a.attrelid = r.oid
                  and a.atttypid = t.oid
                  and t.typname = 'bytea'
            """ % (TD["table_name"], TD["table_schema"])
        rows = plpy.execute(q)
        if rows and len(rows) > 0:
            bytea_cols = [r["attname"] for r in rows]
        else:
            bytea_cols = []
        for k in TD["new"].keys():
            if TD["new"][k] != TD["old"][k]:
                if k in bytea_cols:
                    zmena = "%s: MODIFIED" % k
                else:
                    zmena = """%s: %s -> %s""" % (k, pg_escape(str(TD["old"][k])),
                                                  pg_escape(str(TD["new"][k])))
                zmeny.append(zmena)
        if zmeny != []:        
            zmenystr = """\n""".join(zmeny)        
            q = """insert into _updates (tabulka, klic, zmeny)
                   select '%s', '%s', '%s'
                """ % (tabulka, klicestr, zmenystr)
            q = plpy.execute(q)
        return None


class LogTrigger(sql.SQLPlFunction):
    name = 'log_trigger'
    arguments = ()
    result_type = sql.G_CONVERT_THIS_FUNCTION_TO_TRIGGER
    multirow = False
    security_definer = True
    stability = 'VOLATILE'
    depends_on = ()
    access_rights = ()

    def body(self):
        return """
declare
  id_ int;
  current_record record;
  c text;
  cc text;
  t text;
  v text;
  key_column_ text := tg_argv[0];
  key_value_ text := null;
  detail_ text := '';
  changed bool;
begin
  if tg_op = 'DELETE' then
    current_record := old;
  else
    current_record := new;
  end if;
  for c in select regexp_split_to_table(key_column_, ', *') loop
    cc := quote_ident(c);
    execute concat('select $1.', cc, '::text') into strict v using current_record;
    if key_value_ is null then
      key_value_ := v;
    else
      key_value_ := concat(key_value_, ',', v);
    end if;
  end loop;
  for c, t in select a.attname, t.typname
              from pg_class r, pg_namespace nsp, pg_attribute a, pg_type t
              where r.relname = tg_table_name and r.relnamespace = nsp.oid and nsp.nspname = tg_table_schema and
                    a.attrelid = r.oid and a.atttypid = t.oid and a.attnum > 0
  loop
    cc := quote_ident(c);
    if tg_op = 'UPDATE' then
      execute concat('select coalesce($1.', cc, '::text, '''') != coalesce($2.', cc, '::text, '''')') into strict changed using old, new;
      if changed then
        if detail_ != '' then
          detail_ := concat(detail_, '
');
        end if;
        execute concat('select
                       (case when $1.', cc, ' is not null and $3 = ''bytea'' then ''BINARY'' when $1.', cc, ' is null then ''NULL'' else $1.', cc, '::text end) ||
                 '' -> '' ||
                       (case when $2.', cc, ' is not null and $3 = ''bytea'' then ''BINARY'' when $2.', cc, ' is null then ''NULL'' else $2.', cc, '::text end)')
                into strict v using old, new, t;
        detail_ := concat(detail_, c, ': ', v);
      end if;
    else
      execute concat('select $1.', cc, ' is not null') into strict changed using current_record;
      if changed then
        if detail_ != '' then
          detail_ := concat(detail_, '
');
        end if;
        execute concat('select (case when $1.', cc, ' is not null and $2 = ''bytea'' then ''BINARY'' else $1.', cc, '::text end)')
                into strict v using current_record, t;
        detail_ := concat(detail_, c, ': ', v);
      end if;
    end if;
  end loop;
  if tg_op != 'UPDATE' or detail_ != '' then
    insert into t_changes (timestamp, username, schemaname, tablename, operation, key_column, key_value)
           values (now(), session_user, tg_table_schema, tg_table_name, tg_op, key_column_, key_value_)
           returning id into strict id_;
    insert into t_changes_detail (id, detail) values (id_, detail_);
  end if;
  return null;
end;
"""

class Base_LogTrigger(sql.SQLTrigger):
    name = 'log'
    events = ('insert', 'update', 'delete',)
    body = LogTrigger

class Base_LogSQLTable(sql.SQLTable):
    @property
    def triggers(self):
        keys = ','.join([f.id() for f in self.fields if f.primary_key()])
        return ((Base_LogTrigger, keys,),)
