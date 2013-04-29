# -*- coding: utf-8 -*-

"""Gensql definitions for dynamic application menus and access rights."""

from pytis.util import translate as _

db_rights = globals().get('Gall_pytis', None)
if not db_rights:
    raise ProgramError('No rights specified! Please define Gall_pytis')


_std_table_nolog('e_pytis_disabled_dmp_triggers',
      (P('id', TUser),),
      grant=db_rights,
      doc="""This table allows disabling some trigger calls.
Supported values (flags) are:
genmenu -- initial insertion and deletion on certain tables
positions -- set during trigger update of menu positions to prevent recursive trigger calls;
  note this way of doing it is not safe in case of parallel table updates
redundancy -- set during rights redundancy update to prevent recursive trigger calls;
  note this way of doing it is not safe in case of parallel table updates
""")

### Roles

_std_table_nolog('c_pytis_role_purposes',
                 (P('purposeid', pytis.data.String(minlen=4, maxlen=4)),
                  C('purpose', pytis.data.String(maxlen=32), constraints=('unique', 'not null',)),),
                 """There are three kinds of roles:
1. Menu and access administrator roles.  Definitions of these roles may be changed
   only by the database administrators.
2. Roles corresponding to system accounts (login roles).
3. Pure application roles.
""",
                 init_values=(("'admn'", "'Správcovská'",),
                              ("'user'", "'Uživatelská'",),
                              ("'appl'", "'Aplikační'",),),
                 grant=db_rights
                 )

_std_table('e_pytis_roles',
           (P('name', TUser),
            C('description', pytis.data.String(maxlen=64)),
            C('purposeid', pytis.data.String(minlen=4, maxlen=4), constraints=('not null',), default="'appl'",
              references='c_pytis_role_purposes'),
            C('deleted', TDate),),
           init_values=(("'*'", "'Zástupná role pro všechny role'", "'admn'", 'NULL',),
                        ("'admin_roles'", "'Administrátor rolí'", "'admn'", 'NULL',),
                        ("'admin_menu'", "'Administrátor menu'", "'admn'", 'NULL',),
                        ("'admin'", "'Administrátor rolí a menu'", "'admn'", 'NULL',),
                        ("'__pytis'", "'Zástupná role pro číselník sloupců'", "'admn'", 'NULL',),
                        ),
           grant=db_rights,
           doc="Application user roles.",
           depends=('c_pytis_role_purposes',))

def e_pytis_roles_trigger():
    class Roles(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_roles(self):
            plpy.execute("select pytis_update_transitive_roles()")
        def _do_after_insert(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            role = self._pg_escape(self._new['name'])
            plpy.execute("insert into a_pytis_valid_role_members(roleid, member) values ('%s', '%s')" %
                         (role, role,))
        def _do_after_update(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            if self._new['deleted'] != self._old['deleted']:
                self._update_roles()
        def _do_after_delete(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            self._update_roles()
    roles = Roles(TD)
    return roles.do_trigger()

_trigger_function('e_pytis_roles_trigger', body=e_pytis_roles_trigger,
                  depends=('e_pytis_roles', 'e_pytis_disabled_dmp_triggers', 'a_pytis_valid_role_members',
                           'pytis_update_transitive_roles',))

sql_raw("""
create trigger e_pytis_roles_update_after after insert or update or delete on e_pytis_roles
for each row execute procedure e_pytis_roles_trigger();
""",
        name='e_pytis_roles_triggers',
        depends=('e_pytis_roles_trigger',))

viewng('ev_pytis_valid_roles',
       (SelectRelation('e_pytis_roles', alias='main',
                       condition='main.deleted is null or main.deleted > now()'),
        SelectRelation('c_pytis_role_purposes', alias='codebook', exclude_columns=('purposeid',),
                       condition='main.purposeid = codebook.purposeid', jointype=JoinType.INNER),
        ),
       grant=db_rights,
       insert_order=('e_pytis_roles',),
       update_order=('e_pytis_roles',),
       delete_order=('e_pytis_roles',),
       depends=('e_pytis_roles', 'c_pytis_role_purposes',)
       )

viewng('ev_pytis_roles',
       (SelectRelation('e_pytis_roles', alias='t1'),
        SelectRelation('c_pytis_role_purposes', alias='t2', exclude_columns=('purposeid',),
                       condition='t1.purposeid = t2.purposeid', jointype=JoinType.INNER),
        ),
       insert_order=('e_pytis_roles',),
       update_order=('e_pytis_roles',),
       delete_order=('e_pytis_roles',),
       grant=db_rights,
       depends=('e_pytis_roles', 'c_pytis_role_purposes',)
       )

_std_table('e_pytis_role_members',
           (P('id', TSerial,
              doc="Just to make logging happy"),
            C('roleid', TUser, constraints=('not null',), references='e_pytis_roles on update cascade'),
            C('member', TUser, constraints=('not null',), references='e_pytis_roles on update cascade'),
            ),
           """Mutual memberships of roles.
Entries in this table define members of each roleid.
""",
           init_values=(('-1', "'admin_roles'", "'admin'",),
                        ('-2', "'admin_menu'", "'admin'",),
                        ),
           grant=db_rights,
           depends=('e_pytis_roles',))
def e_pytis_role_members_trigger():
    class Roles(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_roles(self):
            plpy.execute("select pytis_update_transitive_roles()")
        def _update_redundancy(self):
            plpy.execute("select pytis_update_rights_redundancy()")
        def _update_all(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            self._update_roles()
            self._update_redundancy()
        def _do_after_insert(self):
            self._update_all()
        def _do_after_update(self):
            self._update_all()
        def _do_after_delete(self):
            self._update_all()
    roles = Roles(TD)
    return roles.do_trigger()

_trigger_function('e_pytis_role_members_trigger', body=e_pytis_role_members_trigger,
                  depends=('e_pytis_role_members', 'e_pytis_disabled_dmp_triggers', 'a_pytis_valid_role_members',
                           'pytis_update_transitive_roles', 'pytis_update_rights_redundancy',))

sql_raw("""
create trigger e_pytis_role_members_all_after after insert or update or delete on e_pytis_role_members
for each row execute procedure e_pytis_role_members_trigger();
""",
        name='e_pytis_role_members_triggers',
        depends=('e_pytis_role_members_trigger',))

viewng('ev_pytis_valid_role_members',
       (SelectRelation('e_pytis_role_members', alias='main'),
        SelectRelation('ev_pytis_valid_roles', alias='roles1',
                       condition='roles1.name = main.roleid', jointype=JoinType.INNER),
        SelectRelation('ev_pytis_valid_roles', alias='roles2',
                       column_aliases=(('name', 'mname',),
                                       ('description', 'mdescription',),
                                       ('purposeid', 'mpurposeid',),
                                       ('purpose', 'mpurpose',),
                                       ('deleted', 'mdeleted',),),
                       condition='roles2.name = main.member', jointype=JoinType.INNER),
        ),
       insert_order=('e_pytis_role_members',),
       update_order=('e_pytis_role_members',),
       delete_order=('e_pytis_role_members',),
       grant=db_rights,
       depends=('e_pytis_role_members', 'ev_pytis_valid_roles',)
       )

_std_table_nolog('a_pytis_valid_role_members',
                 (C('roleid', TUser, constraints=('not null',), references='e_pytis_roles on delete cascade on update cascade'),
                  C('member', TUser, constraints=('not null',), references='e_pytis_roles on delete cascade on update cascade'),),
                 """Complete membership of roles, including transitive relations.
This table is modified only by triggers.
""",
                 depends=('e_pytis_roles',))
def pytis_update_transitive_roles():
    membership = {}
    for row in plpy.execute("select name from ev_pytis_valid_roles"):
        role = row['name']
        membership[role] = []
    for row in plpy.execute("select name, mname from ev_pytis_valid_role_members"):
        role = row['name']
        member = row['mname']
        membership[member].append(role)
    total_membership = {}
    for role in membership.keys():
        all_roles = []
        new_roles = [role]
        while new_roles:
            r = new_roles.pop()
            if r in all_roles:
                continue
            all_roles.append(r)
            new_roles += membership.get(r, [])
        total_membership[role] = all_roles
    def _pg_escape(val):
        return str(val).replace("'", "''")
    plpy.execute("delete from a_pytis_valid_role_members")
    for role, total_roles in total_membership.items():
        for total in total_roles:
            plpy.execute("insert into a_pytis_valid_role_members (roleid, member) values ('%s', '%s')" %
                         (_pg_escape(total), _pg_escape(role)))
    return True

_plpy_function('pytis_update_transitive_roles', (), TBoolean,
               body=pytis_update_transitive_roles)

function('pytis_copy_role', (TString, TString), 'void',
         """
delete from e_pytis_role_members
       where member=$2 and roleid in (select roleid from e_pytis_roles where purposeid=''appl'');
insert into e_pytis_role_members (roleid, member)
       select roleid, $2 as member from e_pytis_role_members left join e_pytis_roles on roleid=name
              where member=$1 and purposeid=''appl'';
""",
         doc="Make application roles of a user the same as those of another user.",
         grant=db_rights,
         depends=('e_pytis_roles', 'e_pytis_role_members',))

function('pytis_user', (), TUser,
         body="""
select user;
""",
         doc="""Return current pytis user.
By redefining this function, debugging of user behavior or sulogin may be possible.""")


### Actions

_std_table_nolog('c_pytis_action_types',
                 (P('type', pytis.data.String(minlen=4, maxlen=4)),
                  C('description', TString),
                  ),
                 """List of defined action types.""",
                 init_values=(("'----'", _(u"''"),),
                              ("'item'", _(u"'Položka menu'"),),
                              ("'menu'", _(u"'Menu'"),),
                              ("'sepa'", _(u"'Separátor'"),),
                              ("'spec'", _(u"'Specifikace'"),),
                              ("'subf'", _(u"'Podformulář'"),),
                              ("'proc'", _(u"'Procedura'"),),
                              ("'actf'", _(u"'Akce formuláře'"),),
                              ("'prnt'", _(u"'Tisk'"),),
                              ),
                 grant=db_rights
                 )
_std_table_nolog('c_pytis_menu_actions',
                 (P('fullname', TString),
                  C('shortname', TString, constraints=('not null',)),
                  C('action_title', TString),
                  C('description', TString),
                  C('parent_action', TString),
                  # Redundant column computed by c_pytis_menu_actions_trigger_before.
                  C('spec_name', TString), 
                  ),
                 """List of available application actions.""",
                 grant=db_rights
                 )
def c_pytis_menu_actions_trigger():
    class Menu(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_all(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            plpy.execute("select pytis_update_actions_structure()")
        def _do_after_insert(self):
            self._update_all()
        def _do_after_update(self):
            self._update_all()
        def _do_after_delete(self):
            self._update_all()
    menu = Menu(TD)
    return menu.do_trigger()

_trigger_function('c_pytis_menu_actions_trigger', body=c_pytis_menu_actions_trigger,
                  depends=('c_pytis_menu_actions', 'pytis_update_actions_structure', 'e_pytis_disabled_dmp_triggers',))

sql_raw("""
create or replace function c_pytis_menu_actions_trigger_before() returns trigger as $$
declare
    kind text;
begin
    kind := split_part(new.shortname, '/', 1);
    new.spec_name = null;
    if kind in ('action', 'proc', 'print') then
       new.spec_name = split_part(new.shortname, '/', 3);
    end if;
    if kind in ('form', 'NEW_RECORD', 'handle') then
       new.spec_name = split_part(new.shortname, '/', 2);
    end if;
    return new;
end;
$$ language plpgsql;
""", name='c_pytis_menu_actions_trigger_before')

sql_raw("""
create trigger c_pytis_menu_actions_all_after_rights after insert or update or delete on c_pytis_menu_actions
for each statement execute procedure c_pytis_menu_actions_trigger();

create trigger c_pytis_menu_actions_all_trigger_before before insert or update on c_pytis_menu_actions
for each row execute procedure c_pytis_menu_actions_trigger_before();
""",
        name='c_pytis_menu_actions_triggers',
        depends=('c_pytis_menu_actions_trigger', 'c_pytis_menu_actions_trigger_before'))

sql_raw("""
create or replace view ev_pytis_short_actions
as select distinct shortname from c_pytis_menu_actions ORDER BY c_pytis_menu_actions.shortname;
""",
        name='ev_pytis_short_actions',
        depends=('c_pytis_menu_actions',))

def pytis_convert_system_rights(shortname):
    shortname = args[0]
    q = """select count(*) as pocet from e_pytis_action_rights
            where shortname='%s' and system=True
        """ % shortname
    result = plpy.execute(q)
    if result[0]["pocet"] == 0:
        plpy.error('No system rights found for %s' % shortname)
    result = plpy.execute(q)
    temp_old = plpy.execute("select new_tempname() as jmeno")[0]["jmeno"]
    temp_new = plpy.execute("select new_tempname() as jmeno")[0]["jmeno"]
    q = """create temp table %s as select * from pytis_view_summary_rights('%s', NULL, False, False)
        """ % (temp_old, shortname)
    result = plpy.execute(q)
    q = "delete from e_pytis_action_rights where shortname='%s' and redundant" % (shortname,)
    plpy.execute(q)
    q = """insert into e_pytis_action_rights (shortname, roleid, rightid, granted, system)
           values ('%s', '*', '*', False, False)
        """ % shortname
    plpy.execute(q)
    q = """update e_pytis_action_rights set system=False
            where shortname='%s' and system=True
        """ % shortname
    plpy.execute(q)
    q = "select pytis_update_summary_rights()"
    plpy.execute(q)
    q = """create temp table %s as select * from pytis_view_summary_rights('%s', NULL, False, False)
        """ % (temp_new, shortname)
    result = plpy.execute(q)
    q = """select * from %s except select * from %s
            union
           select * from %s except select * from %s
        """ % (temp_old, temp_new, temp_new, temp_old)
    result = plpy.execute(q)
    if len(result) > 0:
        msg = "Converted rights are not the same as original rights"
        plpy.error(msg)
        
_plpy_function('pytis_convert_system_rights', (TString,), 'void',
               body=pytis_convert_system_rights,
               depends=('e_pytis_action_rights',))    


### Menus

_std_table('e_pytis_menu',
           (P('menuid', TSerial),
            C('name', TString, constraints=('unique',),
              doc="Unique identifiers of terminal menu items.  NULL for non-terminal items and separators."),
            C('title', pytis.data.String(maxlen=64),
              doc='User title of the item. If NULL then it is a separator.'),
            C('position', TLTree, constraints=('unique',),
              index=dict(method='gist'),
              doc=("Unique identifier of menu item placement within menu. "
                   "The top-menu item position is ''. "
                   "Each submenu has exactly one label more than its parent. ")),
            C('next_position', TLTree, constraints=('unique',),
              default="'dummy'",
              doc=("Free position just after this menu item.")),
            C('fullname', TString, references='c_pytis_menu_actions on update cascade',
              doc=("Application action assigned to the menu item."
                   "Menu items bound to submenus should have this value NULL; "
                   "if they do not, the assigned action is ignored.")),
            C('help', TString,
              doc=("Arbitrary single-line help string.")),
            C('hotkey', TString,
              doc=("Sequence of command keys, separated by single spaces."
                   "The space key is represented by SPC string.")),
            C('locked', TBoolean,
              doc=("Iff true, this item may not be edited.")),
            ),
           """Menu structure definition.""",
           grant=db_rights,
           depends=('c_pytis_menu_actions',))
def e_pytis_menu_trigger():
    class Menu(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        ## BEFORE
        def _maybe_new_action(self, old=None):
            if not self._new['name'] and self._new['title'] and (old is None or not old['title']):
                # New non-terminal menu item
                self._new['fullname'] = action = 'menu/' + str(self._new['menuid'])
                if not plpy.execute("select * from c_pytis_menu_actions where fullname='%s'" %
                                    (self._pg_escape(action),)):
                    plpy.execute(("insert into c_pytis_menu_actions (fullname, shortname, description) "
                              "values ('%s', '%s', '%s')") % (action, action, self._pg_escape("Menu '%s'" % (self._new['title'])),))
                    self._return_code = self._RETURN_CODE_MODYFY
        def _check_parent(self, old_position=None):
            # Prevent menu item movement to non-existent parents or to self
            new_position = self._new['position']
            if new_position == old_position:
                return
            if old_position is not None:
                if (new_position[:len(old_position)] == old_position and
                    (len(new_position) == len(old_position) or
                     new_position[len(old_position)] == '.')):
                    raise Exception('error', "Can't move menu item to itself")
            components = new_position.split('.')
            import string
            parent = string.join(components[:-1], '.')
            if parent and not plpy.execute("select menuid from e_pytis_menu where position='%s'" % (parent,)):
                raise Exception('error', "No menu item parent")
        def _do_before_insert(self):
            self._maybe_new_action()
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            self._check_parent()
        def _do_before_update(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='positions'"):
                return
            self._check_parent(self._old['position'])
            self._maybe_new_action(old=self._old)
        def _do_before_delete(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            # If there are any children, reject deletion
            old_position = self._old['position']
            data = plpy.execute("select * from e_pytis_menu where position ~ '%s.*' and position != '%s'" %
                                (old_position, old_position,),
                                1)
            if data:
                self._return_code = self._RETURN_CODE_SKIP
        ## AFTER      
        def _update_positions(self, new=None, old=None):
            if old and new and old['position'] == new['position'] and old['next_position'] == new['next_position']:
                return
            plpy.execute('lock e_pytis_menu in exclusive mode')
            if old and new:
                old_position = old['position']
                new_position = new['position']
                if old_position != new_position:
                    plpy.execute("update e_pytis_menu set position='%s'||subpath(position, nlevel('%s')) where position <@ '%s'" %
                                 (new_position, old_position, old_position,))
            if new:
                data = plpy.execute("select position, next_position from e_pytis_menu where position != '' order by position")
                sequences = {}
                for row in data:
                    position = row['position'].split('.')
                    next_position = row['next_position'].split('.')
                    position_stamp = tuple(position[:-1])
                    if position_stamp not in sequences:
                        sequences[position_stamp] = []
                    sequences[position_stamp].append((position, next_position,))
                import string
                def update_next_position(position, next_position):
                    plpy.execute("update e_pytis_menu set next_position='%s' where position='%s'" %
                                 (string.join(next_position, '.'), string.join(position, '.'),))
                for position_list in sequences.values():
                    position_list_len = len(position_list)
                    for i in range(position_list_len - 1):
                        position, next_position = position_list[i]
                        next_item_position = position_list[i+1][0]
                        if (len(position) != len(next_position) or
                            position >= next_position or
                            next_position >= next_item_position):
                            suffix = position[-1]
                            next_suffix = next_item_position[-1]
                            suffix += '0' * max(len(next_suffix) - len(suffix), 0)
                            next_suffix += '0' * max(len(suffix) - len(next_suffix), 0)
                            new_suffix = str(long((long(suffix) + long(next_suffix)) / 2))
                            while len(new_suffix) < len(next_suffix):
                                new_suffix = '0' + new_suffix
                            if new_suffix == suffix:
                                new_suffix = suffix + '4'
                            next_position = position[:-1] + [new_suffix]
                            update_next_position(position, next_position)
                    last_item = position_list[position_list_len - 1]
                    position, next_position = last_item
                    if (len(position) != len(next_position) or
                        position >= next_position):
                        suffix = position[-1]
                        if suffix[-1] == '9':
                            next_position = position[:-1] + [position[-1] + '4']
                        else:
                            next_position = position[:-1] + [str(long(position[-1]) + 1)]
                        update_next_position(position, next_position)
            plpy.execute("select e_pytis_menu_check_positions()")
        def _do_after_insert(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='import'"):
                return
            plpy.execute("insert into e_pytis_disabled_dmp_triggers (id) values ('positions')")
            self._update_positions(new=self._new)
            plpy.execute("delete from e_pytis_disabled_dmp_triggers where id='positions'")
        def _do_after_update(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='positions'"):
                return
            plpy.execute("insert into e_pytis_disabled_dmp_triggers (id) values ('positions')")
            if not self._new['name'] and self._old['title'] and not self._new['title']:
                # Non-terminal item changed to separator
                plpy.execute("delete from c_pytis_menu_actions where fullname = '%s'" % (self._old['fullname'],))
                plpy.execute("delete from e_pytis_action_rights where shortname = '%s'" % (self._old['fullname'],))
            self._update_positions(new=self._new, old=self._old)
            plpy.execute("delete from e_pytis_disabled_dmp_triggers where id='positions'")
        def _do_after_delete(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='import'"):
                return
            plpy.execute("insert into e_pytis_disabled_dmp_triggers (id) values ('positions')")
            if not self._old['name'] and self._old['title']:
                # Non-terminal menu item
                plpy.execute("delete from c_pytis_menu_actions where fullname = '%s'" % (self._old['fullname'],))
                plpy.execute("delete from e_pytis_action_rights where shortname = '%s'" % (self._old['fullname'],))
            self._update_positions(old=self._old)
            plpy.execute("delete from e_pytis_disabled_dmp_triggers where id='positions'")
    menu = Menu(TD)
    return menu.do_trigger()

_trigger_function('e_pytis_menu_trigger', body=e_pytis_menu_trigger,
                  depends=('e_pytis_menu', 'c_pytis_menu_actions', 'e_pytis_disabled_dmp_triggers',))

sql_raw("""
create trigger e_pytis_menu_all_before before insert or update or delete on e_pytis_menu
for each row execute procedure e_pytis_menu_trigger();
create trigger e_pytis_menu_all_after after insert or update or delete on e_pytis_menu
for each row execute procedure e_pytis_menu_trigger();
""",
        name='e_pytis_menu_triggers',
        depends=('e_pytis_menu_trigger',))

sql_raw("""
create or replace function e_pytis_menu_check_positions() returns void as $$
begin
  if (select count(*)>0 from (select position from e_pytis_menu intersect select next_position from e_pytis_menu) positions) then
    raise exception 'position / next_position conflict';
  end if;
end;
$$ language plpgsql;

create or replace function e_pytis_menu_check_trigger() returns trigger as $$
begin
  if (select count(*)=0 from e_pytis_disabled_dmp_triggers where id='positions') then
    perform e_pytis_menu_check_positions();
  end if;
  return null;
end;
$$ language plpgsql;
create trigger e_pytis_menu_zcheck_after after insert or update or delete on e_pytis_menu
for each statement execute procedure e_pytis_menu_check_trigger();
""",
        name='e_pytis_menu_special_triggers',
        depends=('e_pytis_menu',))

def e_pytis_menu_trigger_rights():
    class Menu(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_all(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu' or id='positions'"):
                return
            plpy.execute("select pytis_update_actions_structure()")
        def _do_after_insert(self):
            self._update_all()
        def _do_after_update(self):
            self._update_all()
        def _do_after_delete(self):
            self._update_all()
    menu = Menu(TD)
    return menu.do_trigger()

_trigger_function('e_pytis_menu_trigger_rights', body=e_pytis_menu_trigger_rights,
                  depends=('e_pytis_menu', 'pytis_update_actions_structure', 'e_pytis_disabled_dmp_triggers',))

sql_raw("""
create trigger e_pytis_menu_all_after_rights after insert or update or delete on e_pytis_menu
for each statement execute procedure e_pytis_menu_trigger_rights();
""",
        name='e_pytis_menu_triggers_rights',
        depends=('e_pytis_menu_trigger_rights',))

viewng('ev_pytis_menu',
       (SelectRelation('e_pytis_menu', alias='main', exclude_columns=('fullname',)),
        SelectRelation('c_pytis_menu_actions', alias='actions',
                       exclude_columns=('description', 'spec_name', 'parent_action',),
                       condition='main.fullname = actions.fullname', jointype=JoinType.LEFT_OUTER),
        ),
       include_columns=(V(None, 'position_nsub',
                          "(select count(*)-1 from e_pytis_menu where position <@ main.position)"),
                        V(None, 'xtitle',
                          u"coalesce(main.title, '――――')"),),
       insert_order=('e_pytis_menu',),
       update_order=('e_pytis_menu',),
       delete_order=('e_pytis_menu',),
       grant=db_rights,
       depends=('e_pytis_menu', 'c_pytis_menu_actions',)
       )

viewng('ev_pytis_menu_structure',
       (SelectRelation('a_pytis_actions_structure', alias='structure',
                       exclude_columns=('menuid', 'summary_id', 'summaryid',)),
        SelectRelation('e_pytis_menu', alias='menu', exclude_columns=('name', 'fullname', 'position', 'title',),
                       condition='structure.menuid = menu.menuid', jointype=JoinType.LEFT_OUTER),
        SelectRelation('c_pytis_action_types', alias='atypes', exclude_columns=('type',),
                       column_aliases=(('description', 'actiontype',),),
                       condition='structure.type = atypes.type', jointype=JoinType.LEFT_OUTER),
        SelectRelation('c_pytis_menu_actions', alias='actions',
                       exclude_columns=('fullname', 'shortname', 'action_title', 'spec_name', 'parent_action',),
                       condition='structure.fullname = actions.fullname', jointype=JoinType.LEFT_OUTER)
        ),
       include_columns=(V(None, 'position_nsub',
                          "(select count(*)-1 from a_pytis_actions_structure where position <@ structure.position)"),
                        V(None, 'title',
                          "coalesce(menu.title, '('||actions.action_title||')')"),
                        ),
       insert_order=(),
       update_order=('c_pytis_menu_actions',),
       delete_order=(),
       grant=db_rights,
       depends=('e_pytis_menu', 'a_pytis_actions_structure', 'c_pytis_menu_actions',)
       )

def pytis_first_position(position):
    position = args[0]
    start = '1' + '0' * (len(position) - 1)
    first = str(long((long(start) + long(position)) / 2))
    if first == start:
        first += '8'
    return first

_plpy_function('pytis_first_position', (TString,), TString,
               body=pytis_first_position,
               depends=())
viewng('ev_pytis_menu_all_positions',
       (SelectSet(Select((SelectRelation('e_pytis_menu', alias='menu1', exclude_columns=('*',),
                                         condition=""),),
                         include_columns=(V(None, 'position', 'position'),
                                          V(None, 'xtitle', u"coalesce(menu1.title, '――――')"),
                                          ))),
        SelectSet(Select((SelectRelation('e_pytis_menu', alias='menu2', exclude_columns=('*',),
                                         condition="position != ''"),),
                         include_columns=(V(None, 'position', "next_position"),
                                          V(None, 'xtitle', "''"),
                                          )),
                  settype=UNION),
        SelectSet(Select((SelectRelation('e_pytis_menu', alias='menu3', exclude_columns=('*',),
                                         condition="name is NULL and title is not NULL"),),
                         include_columns=(V(None, 'position', "menu3.position||pytis_first_position(subpath((select position from e_pytis_menu where position <@ menu3.position and position != menu3.position union select '9' order by position limit 1), -1)::text)::ltree"),
                                          V(None, 'xtitle', "''"),
                                          )),
                  settype=UNION),),
       insert=(),
       update=(),
       delete=(),
       grant=db_rights,
       depends=('e_pytis_menu', 'pytis_first_position',))

viewng('ev_pytis_menu_positions',
       (SelectRelation('ev_pytis_menu_all_positions', alias='positions'),
        SelectRelation('e_pytis_menu', alias='menu', exclude_columns=('name', 'fullname', 'position', 'hotkey', 'help', 'locked',),
                       condition='positions.position = menu.position', jointype=JoinType.LEFT_OUTER),),
       insert_order=(),
       update_order=(),
       delete_order=(),
       grant=db_rights,
       depends=('ev_pytis_menu', 'ev_pytis_menu_all_positions',)
       )


### Access rights

_std_table_nolog('c_pytis_access_rights',
                 (P('rightid', pytis.data.String(maxlen=8)),
                  C('description', pytis.data.String(), constraints=('not null',)),
                  ),
                 """Available rights.  Not all rights make sense for all actions and menus.""",
                 init_values=(("'*'", _(u"'Všechna práva'"),),
                              ("'show'", _(u"'Viditelnost položek menu'"),),
                              ("'view'", _(u"'Prohlížení existujících záznamů'"),),
                              ("'insert'", _(u"'Vkládání nových záznamů'"),),
                              ("'update'", _(u"'Editace existujících záznamů'"),),
                              ("'delete'", _(u"'Mazání záznamů'"),),
                              ("'print'", _(u"'Tisky'"),),
                              ("'export'", _(u"'Exporty'"),),
                              ("'call'", _(u"'Spouštění aplikačních procedur'"),),
                              ),
                 grant=db_rights)

_std_table('e_pytis_action_rights',
           (P('id', TSerial,
              doc="Just to make logging happy"),
            C('shortname', TString, constraints=('not null',)),
            C('roleid', TUser, references='e_pytis_roles on update cascade', constraints=('not null',)),
            C('rightid', pytis.data.String(maxlen=8), references='c_pytis_access_rights on update cascade', constraints=('not null',)),
            C('colname', TUser),
            C('system', TBoolean, constraints=('not null',), default="'f'",
              doc="Iff true, this is a system (noneditable) permission."),
            C('granted', TBoolean, constraints=('not null',), default="'t'",
              doc="If true the right is granted, otherwise it is denied; system rights are always granted."),
            C('redundant', TBoolean, default="'f'",
              doc="If true, the right is redundant in the current set of access rights."),
            C('status', 'smallint', default='1', constraints=('not null',),
              doc="""Status of the right: 0 = current; -1 = old (to be deleted after the next global rights update);
1 = new (not yet active, to be activated after the next global rights update)."""
              ),
            ),
           sql=("unique (shortname, roleid, rightid, colname, system, granted, status)"),
           doc="""Assignments of access rights to actions.

Extent of each action right is strictly limited by its granted system
permissions.  Non-system rights can only further limit the system rights.  If
there is no system permission for a given action, the action is forbidden.  The
resulting right is not broader than the intersection of all the related
permissions.

Some actions, e.g. dual form actions, form its access rights set by inclusion
of other action rights.

Access rights of non-terminal menu items, identified by action name
'menu/MENUID' define default rights, used when no non-system access right
definition is present for a terminal item.  More nested access rights of
non-terminal menu items have higher precedence.

Action rights are supported and used in the application, but they are not
exposed in the current user interface directly.  In future they may also
support extended rights assignment, e.g. in context menus etc.
""",
           grant=db_rights,
           depends=('c_pytis_menu_actions', 'e_pytis_roles', 'c_pytis_access_rights',)
           )
def pytis_update_rights_redundancy():
    plpy.execute("insert into e_pytis_disabled_dmp_triggers (id) values ('redundancy')")
    roles = {}
    for row in plpy.execute("select roleid, member from a_pytis_valid_role_members"):
        roleid, member = row['roleid'], row['member']
        role_list = roles.get(roleid)
        if role_list is None:
            role_list = roles[roleid] = [roleid]
        role_list.append(member)
    class Right(object):
        properties = ('id', 'shortname', 'roleid', 'rightid', 'granted', 'colname', 'system', 'redundant', 'status',)
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                if k not in ('vytvoril', 'vytvoreno', 'zmenil', 'zmeneno',):
                    if k not in self.properties:
                        raise Exception('programming error', k)
                    setattr(self, k, v)
        def __cmp__(self, other):
            return cmp(self.id, other.id)
        def strong_redundant(self, other):
            for attr in Right.properties:
                if attr not in ('id', 'redundant', 'roleid', 'system', 'granted', 'status',):
                    if getattr(self, attr) != getattr(other, attr):
                        return False
            if self.system and not other.system:
                return False
            if self.roleid not in roles.get(other.roleid, []):
                return False
            if not self.granted and other.granted:
                return False
            return True
        def default_redundant(self, other):
            for attr in Right.properties:
                if attr not in ('id', 'redundant', 'rightid', 'roleid', 'colname', 'system',
                                'granted', 'status',):
                    if getattr(self, attr) != getattr(other, attr):
                        return False
            if self.system and not other.system:
                return False
            if ((self.rightid == other.rightid or other.rightid == '*') and
                (self.roleid in roles.get(other.roleid, []) or other.roleid == '*') and
                (self.colname == other.colname or other.colname is None)):
                if self.granted == other.granted:
                    return True
                else:
                    return other
            return False
        def matches_system_rights(self, system_rights):
            if self.system:
                return True
            if not system_rights:
                return True
            if self.rightid == 'show':
                # Well, there are typically no SHOW system rights...
                return True
            for r in system_rights:
                if ((self.roleid not in roles.get(r.roleid, []) or self.roleid == '*' or r.roleid == '*') and
                    (self.rightid == r.rightid or self.rightid == '*' or r.rightid == '*') and
                    (self.colname == r.colname or self.colname is None or r.colname is None)):
                    return True
            return False
    rights = {}
    for row in plpy.execute("select * from e_pytis_action_rights where status>=0"):
        r = Right(**row)
        comrades = rights.get(r.shortname)
        if comrades is None:
            comrades = rights[r.shortname] = []
        comrades.append(r)
    base_rights = []
    redundant_rights = []
    for key, comrades in rights.items():
        base = []
        while comrades:
            r = comrades.pop()
            for rr in comrades + base:
                if r is not rr and r.strong_redundant(rr):
                    redundant_rights.append(r)
                    break
            else:
                base.append(r)
        rights[key] = base
    for key, comrades in rights.items():
        base = []
        system_rights = [r for r in comrades if r.system]
        for r in comrades:
            if r.matches_system_rights(system_rights):
                base.append(r)
            else:
                redundant_rights.append(r)
        rights[key] = base
    for comrades in rights.values():
        base = set()
        maybe_redundant = []
        sure_redundant = set()
        while comrades:
            r = comrades.pop()
            blockers = set()
            redundant = False
            # If the right differs from all other rights here completely, it's
            # not redundant.  If it is compatible with a default ("star")
            # right, it may be redundant, but only if it doesn't override
            # another non-redundant default right.  This algorithm may not give
            # perfect result, but it's important so that it at least doesn't
            # mark a non-redundant right as redundant.  We only care about
            # specific->general rules interactions; exact matches should be
            # already resolved by the strong redundancy pass, i.e. the graph of
            # blockers should be acyclic (it contains only edges from more
            # specific to less specific rights).
            for rr in comrades + list(base):
                state = r.default_redundant(rr)
                if state is True:
                    redundant = True
                elif state is not False:
                    blockers.add(state)
            if redundant:
                blockers = blockers - sure_redundant
                if blockers:
                    if blockers.intersection(base):
                        base.add(r)
                    else:
                        maybe_redundant.append((r, blockers,))
                else:
                    redundant_rights.append(r)
                    sure_redundant.add(r)
            else:
                base.add(r)
        while maybe_redundant:
            new_maybe_redundant = []
            for r, blockers in maybe_redundant:
                blockers = blockers - sure_redundant
                if blockers:
                    if blockers.intersection(base):
                        base.add(r)
                    else:
                        new_maybe_redundant.append((r, blockers,))
                else:
                    redundant_rights.append(r)
                    sure_redundant.add(r)
            if len(new_maybe_redundant) == len(maybe_redundant):
                for r, blockers in new_maybe_redundant:
                    base.add(r)
                break
            maybe_redundant = new_maybe_redundant
        base_rights += list(base)
    for r in base_rights:
        if r.redundant:
            plpy.execute("update e_pytis_action_rights set redundant='F' where id='%d' and redundant!='F'" % (r.id,))
    for r in redundant_rights:
        if not r.redundant:
            plpy.execute("update e_pytis_action_rights set redundant='T' where id='%d' and redundant!='T'" % (r.id,))
    plpy.execute("delete from e_pytis_disabled_dmp_triggers where id='redundancy'")
_plpy_function('pytis_update_rights_redundancy', (), TBoolean,
               body=pytis_update_rights_redundancy,
               depends=('e_pytis_disabled_dmp_triggers', 'a_pytis_valid_role_members', 'e_pytis_action_rights',))
def e_pytis_action_rights_trigger():
    class Rights(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_redundancy(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='genmenu'"):
                return
            plpy.execute("select pytis_update_rights_redundancy()")
        def _do_before_insert(self):
            if self._new['status'] is None:
                self._new['status'] = 1
                self._return_code = self._RETURN_CODE_MODYFY
        def _do_after_insert(self):
            self._update_redundancy()
        def _do_after_update(self):
            if plpy.execute("select * from e_pytis_disabled_dmp_triggers where id='redundancy'"):
                return
            self._update_redundancy()
        def _do_after_delete(self):
            self._update_redundancy()
    rights = Rights(TD)
    return rights.do_trigger()
_trigger_function('e_pytis_action_rights_trigger', body=e_pytis_action_rights_trigger,
                  depends=('e_pytis_action_rights', 'pytis_update_rights_redundancy', 'e_pytis_disabled_dmp_triggers',))
sql_raw("""
create trigger e_pytis_action_rights_all_before before insert on e_pytis_action_rights
for each row execute procedure e_pytis_action_rights_trigger();
create trigger e_pytis_action_rights_all_after after insert or update or delete on e_pytis_action_rights
for each statement execute procedure e_pytis_action_rights_trigger();
""",
        name='e_pytis_action_rights_triggers',
        depends=('e_pytis_action_rights_trigger',))

viewng('ev_pytis_action_rights',
       (SelectRelation('e_pytis_action_rights', alias='rights', condition="rights.status>=0"),
        SelectRelation('e_pytis_roles', alias='roles', exclude_columns=('*',),
                       condition="rights.roleid = roles.name", jointype=JoinType.LEFT_OUTER),
        SelectRelation('c_pytis_role_purposes', alias='purposes', exclude_columns=('purposeid',),
                       condition="roles.purposeid = purposes.purposeid", jointype=JoinType.LEFT_OUTER),
        ),
       insert_order=('e_pytis_action_rights',),
       update="""(
insert into e_pytis_action_rights (shortname, roleid, rightid, colname, system, granted, status)
       values (new.shortname, new.roleid, new.rightid, new.colname, new.system, new.granted, 1);
update e_pytis_action_rights set status=-1 where id=new.id;
)""",
       delete="""(
delete from e_pytis_action_rights where id=old.id and status=1;
update e_pytis_action_rights set status=-1 where id=old.id and status=0;
)""",
       grant=db_rights,
       depends=('e_pytis_action_rights', 'e_pytis_roles', 'c_pytis_role_purposes',))

sqltype('typ_action_rights_foldable',
        (C('id', TInteger),
         C('roleid', TString),
         C('purpose', TString),
         C('shortname', TString),
         C('colname', TString),
         C('rightid', TString),
         C('system', TBoolean),
         C('granted', TBoolean),
         C('redundant', TBoolean),
         C('tree', 'ltree'),
         C('subcount', TInteger),
         ))
def pytis_action_rights_foldable(shortname, column):
    shortname, column = args
    if column is None:
        column = 'roleid'
    import string
    tree = {}
    if shortname:
        condition = "shortname='%s'" % (shortname,)
    else:
        condition = "true"
    query = ("select id, roleid, purpose, shortname, colname, rightid, system, granted, redundant "
             "from ev_pytis_action_rights where %s" % (condition,))
    for row in plpy.execute(query):
        column_value = row[column]
        column_rows = tree.get(column_value, [])
        column_rows.append(row)
        tree[column_value] = column_rows
    if column == 'roleid':
        other_column = 'colname'
    else:
        other_column = 'roleid'
    result = []
    def ltree_value(value):
        if not value:
            return '_'
        safe_value = []
        for c in value:
            if c not in string.ascii_letters and c not in string.digits:
                c = '_'
            safe_value.append(c)
        return string.join(safe_value, '')
    for column_value, rows in tree.items():
        def maybe_label(target_column):
            if target_column == column:
                label = column_value
            else:
                label = None
            return label
        result.append((-1, maybe_label('roleid'), None, shortname, maybe_label('colname'),
                       maybe_label('rightid'), None, None, None,
                       ltree_value(column_value), len(rows),))
        for row in rows:
            tree_id = ltree_value(column_value) + '.' + ltree_value(row[other_column])
            result.append((row['id'], row['roleid'], row['purpose'], row['shortname'], row['colname'],
                           row['rightid'], row['system'], row['granted'], row['redundant'],
                           tree_id, 0,))
    return result
_plpy_function('pytis_action_rights_foldable', (TString, TString,),
               RT('typ_action_rights_foldable', setof=True),
               body=pytis_action_rights_foldable,
               depends=('ev_pytis_action_rights',),)

viewng('ev_pytis_user_system_rights',
       (SelectRelation('e_pytis_action_rights', alias='rights',
                       condition="rights.system = 'T' and roleid = '*' or roleid in (select roleid from ev_pytis_user_roles)"),
        ),
       grant=db_rights,
       depends=('e_pytis_action_rights', 'ev_pytis_user_roles',))

function('pytis_copy_rights', (TString, TString), 'void',
         """
update e_pytis_action_rights set status=-1 where shortname=$2;
insert into e_pytis_action_rights (shortname, roleid, rightid, colname, system, granted)
       select $2 as shortname, roleid, rightid, colname, system, granted from e_pytis_action_rights
              where shortname=$1 and status>=0;
""",
         doc="Make access rights of a menu item the same as of another menu item.",
         grant=db_rights,
         depends=('e_pytis_action_rights',))

function('pytis_columns_in_rights', (TString,), RT('name', setof=True),
         """
select distinct colname from e_pytis_action_rights where shortname=$1 and colname is not null;
""",
         doc="Return column names appearing in rights assigned to given shortname.",
         grant=db_rights,
         depends=('e_pytis_action_rights',))

function('pytis_remove_redundant', (TString,), 'void',
         """
delete from ev_pytis_action_rights where shortname=$1 and redundant=''t'';
""",
         doc="Remove redundant rights of the given action.",
         grant=db_rights,
         depends=('e_pytis_action_rights',))


### Summarization

function('pytis_actions_lock_id', (), 'bigint',
         """
select 200910081415;
""",
         doc="Id of the advisory lock for a_pytis_actions_structure.",
         grant=db_rights,
         depends=())

sqltype('typ_summary_rights',
        (C('shortname', TString),
         C('roleid', TString),
         C('rights', TString),
         C('columns', TString),))
def pytis_compute_summary_rights(shortname_arg, role_arg, new_arg, multirights_arg, compress_arg):
    shortname_arg, role_arg, new_arg, multirights_arg, compress_arg = args
    import copy, string
    def _pg_escape(val):
        return str(val).replace("'", "''")
    # Retrieve roles
    roles = {}
    query = "select roleid, member from a_pytis_valid_role_members"
    if role_arg:
        query = "%s where member='%s'" % (query, role_arg,)
    for row in plpy.execute(query):
        roleid, member = row['roleid'], row['member']
        members = roles.get(member)
        if members is None:
            roles[member] = members = []
        members.append(roleid)
    # Retrieve rights
    class RawRights(object):
        def __init__(self):
            self.system = set()
            self.allowed = set()
            self.forbidden = set()
    raw_rights = {}
    if new_arg:
        condition = 'status >= 0'
    else:
        condition = 'status <= 0'
    if shortname_arg:
        s = _pg_escape(shortname_arg)
        q = (("select distinct shortname from c_pytis_menu_actions "
              "where shortname='%s' or "
              "substr(fullname, 8) in (select fullname from c_pytis_menu_actions where shortname='%s')")
             % (s, s,))
        related_shortnames_list = ["'%s'" % (_pg_escape(row['shortname']),) for row in plpy.execute(q)]
        if not related_shortnames_list:
            return []
        related_shortnames = string.join(related_shortnames_list, ', ')
        condition = "%s and shortname in (%s)" % (condition, related_shortnames,)
    rights_query = ("select rightid, granted, roleid, shortname, colname, system "
                    "from e_pytis_action_rights "
                    "where %s") % (condition,)
    for row in plpy.execute(rights_query):
        rightid, granted, roleid, shortname, column, system = row['rightid'], row['granted'], row['roleid'], row['shortname'], row['colname'], row['system']
        key = shortname
        item_rights = raw_rights.get(key)
        if item_rights is None:
            raw_rights[key] = item_rights = {}
        role_rights = item_rights.get(roleid)
        if role_rights is None:
            item_rights[roleid] = role_rights = RawRights()
        if system:
            r = role_rights.system
        elif granted:
            r = role_rights.allowed
        else:
            r = role_rights.forbidden
        r.add((rightid, column,))
    # Retrieve subactions
    subactions = {}
    if shortname_arg:
        shortname_condition = "c_pytis_menu_actions.shortname in (%s)" % (related_shortnames,)
        condition = 'fullname in (select fullname from c_pytis_menu_actions where %s)' % (shortname_condition,)
    else:
        shortname_condition = condition = 'true'    
    for row in plpy.execute("select fullname, shortname from c_pytis_menu_actions where fullname like 'sub/%%' and %s order by fullname"
                            % (condition,)):
        fullname, shortname = row['fullname'], row['shortname']
        parent = fullname[fullname.find('/', 4)+1:]
        parent_subactions = subactions.get(parent)
        if parent_subactions is None:
            parent_subactions = subactions[parent] = []
        parent_subactions.append(shortname)
    # Compute rights
    standard_rights = ['view', 'insert', 'update', 'delete', 'print', 'export', 'call']
    class Rights(object):
        def __init__(self, total, allowed, forbidden, subforms, columns):
            self.total = total
            self.allowed = allowed
            self.forbidden = forbidden
            self.subforms = subforms
            self.columns = columns
    computed_rights = {}
    for row in plpy.execute("select fullname, shortname from c_pytis_menu_actions where %s" % (shortname_condition,)):
        shortname, fullname = row['shortname'], row['fullname']
        item_rights = raw_rights.get(shortname, {})
        subforms = subactions.get(fullname, ())
        if shortname[:5] == 'form/' or shortname[:9] == 'RUN_FORM/':
            default_forbidden = set((('call', None,),))
        elif shortname[:7] in ('handle/', 'action/',):
            default_forbidden = set((('view', None,), ('insert', None,), ('update', None,),
                                     ('delete', None,), ('print', None,), ('export', None,),))
        elif shortname[:5] == 'menu/':
            default_forbidden = set((('view', None,), ('insert', None,), ('update', None,), ('delete', None,),
                                     ('print', None,), ('export', None,), ('call', None,),))
        else:
            default_forbidden = set()
        for roleid, role_roles in roles.items():
            columns = {}
            max_rights = set()
            allowed_rights = set()
            forbidden_rights = copy.copy(default_forbidden)
            for role in role_roles:
                raw = item_rights.get(role) or RawRights()
                max_rights.update(raw.system)
                allowed_rights.update(raw.allowed)
                forbidden_rights.update(raw.forbidden)
            allowed_rights.difference_update(forbidden_rights)
            raw_default = item_rights.get('*') or RawRights()
            max_rights.update(raw_default.system)
            forbidden_rights.update(raw_default.forbidden.difference(allowed_rights))
            allowed_rights.update(raw_default.allowed.difference(forbidden_rights))
            for r, c in (allowed_rights.union(max_rights)):
                if not c in columns:
                    columns[c] = set()
                columns[c].add(r)
            for r, c in forbidden_rights:
                if not c in columns:
                    columns[c] = set()
            if not max_rights:
                for r in item_rights.values():
                    if r.system:
                        break
                else:
                    max_rights = set([(r, None,) for r in standard_rights])
            def store_rights(shortname, max_rights, allowed_rights, forbidden_rights):
                if max_rights is None:
                    max_rights = allowed_rights
                rights = set([right for right in max_rights if right not in forbidden_rights and ('*', right[1],) not in forbidden_rights])
                for r in allowed_rights.difference(forbidden_rights):
                    if r in max_rights or (r[0], None,) in max_rights:
                        rights.add(r)
                if ('show', None,) not in forbidden_rights:
                    rights.add(('show', None,))
                computed_rights[(shortname, roleid,)] = Rights(total=rights, allowed=allowed_rights, forbidden=forbidden_rights,
                                                               subforms=subforms, columns=columns)
            store_rights(shortname, max_rights, allowed_rights, forbidden_rights)
    # Output summary rights
    result = []
    for short_key, all_rights in computed_rights.items():
        shortname, roleid = short_key
        if shortname_arg is not None and shortname != shortname_arg:
            continue
        if role_arg is not None and roleid != role_arg:
            continue
        # Multiform view rights are valid if they are permitted by the main
        # form and (in case of the VIEW right) at least one of the side forms.
        total = all_rights.total
        subforms = all_rights.subforms
        if multirights_arg and subforms:
            r = computed_rights.get((subforms[0], roleid,)) # main form
            if r is not None:
                total = set([rr for rr in total if rr in r.total or (rr[0], None,) in r.total])
            subforms_total = set()
            for sub in subforms[1:]:
                r = computed_rights.get((sub, roleid,))
                if r is None:
                    subforms_total = set([(r, None,) for r in standard_rights + ['show']])
                    break
                else:
                    subforms_total.update(r.total)
            all_rights.total = set([r for r in total if r[0] != 'view' or r[0] in [rr[0] for rr in subforms_total]])
        # Format and return the rights
        if compress_arg:
            rights = []
            for r, column in all_rights.total:
                if r not in rights:
                    rights.append(r)
            rights.sort()
            rights_string = string.join(rights, ' ')
            result.append((shortname, roleid, rights_string, ''))
        else:
            rights = all_rights.total
            general_rights = set([r for r, column in rights if column is None])
            column_rights = all_rights.columns
            for r, column in rights:
                if column is not None and r in general_rights:
                    column_rights[column].add(r)
            summarized_rights = {}
            for column, crights in column_rights.items():
                if column is None:
                    continue
                if '*' in crights:
                    crights_list = standard_rights
                else:
                    crights_list = list(crights)
                crights_list = [r for r in crights
                                if (r, None,) in rights or (r, column,) in rights]
                crights_list = crights_list + [r for r in general_rights if (r, column) not in all_rights.forbidden]
                crights_list = list(set(crights_list)) # remove duplicates
                crights_list.sort()
                rights_string = string.join(crights_list, ' ')
                summarized_rights[rights_string] = summarized_rights.get(rights_string, []) + [column]
            general_rights = list(general_rights)
            general_rights.sort()
            summarized_rights[string.join(general_rights, ' ')] = None
            for rights_string, columns in summarized_rights.items():
                if columns is None:
                    columns_string = ''
                else:
                    columns.sort()
                    columns_string = string.join(columns, ' ')
                result.append((shortname, roleid, rights_string, columns_string,))
    return result
_plpy_function('pytis_compute_summary_rights', (TString, TString, TBoolean, TBoolean, TBoolean,),
               RT('typ_summary_rights', setof=True),
               body=pytis_compute_summary_rights,
               depends=('a_pytis_valid_role_members', 'e_pytis_action_rights',),)

function('pytis_update_summary_rights', (), 'void',
         body="""
delete from e_pytis_action_rights where status<0;
update e_pytis_action_rights set status=0 where status>0;
""",
         grant=db_rights,
         depends=('e_pytis_action_rights',))

_std_table_nolog('a_pytis_actions_structure',
                 (C('fullname', TString, constraints=('not null',)),
                  C('shortname', TString, constraints=('not null',)),
                  C('menuid', TInteger),
                  C('position', TLTree, constraints=('not null',),
                    index=dict(method='gist')),
                  C('type', pytis.data.String(minlen=4, maxlen=4), constraints=('not null',),
                    references='c_pytis_action_types'),
                  C('summaryid', TString),
                  ),
                 """Precomputed actions structure as presented to menu admin.
Item positions and indentations are determined by positions.
This table is modified only by triggers.
""",
                 depends=('c_pytis_action_types',))

def pytis_update_actions_structure():
    for row in plpy.execute("select pytis_actions_lock_id() as lock_id"):
        lock_id = row['lock_id']
    plpy.execute("select pg_advisory_lock(%s)" % (lock_id,))
    try:
        import string
        def _pg_escape(val):
            return str(val).replace("'", "''")
        plpy.execute("delete from a_pytis_actions_structure")
        subactions = {}
        for row in plpy.execute("select fullname, shortname from c_pytis_menu_actions where fullname like 'sub/%' order by fullname"):
            fullname, shortname = row['fullname'], row['shortname']
            parent = fullname[fullname.find('/', 4)+1:]
            parent_subactions = subactions.get(parent)
            if parent_subactions is None:
                parent_subactions = subactions[parent] = []
            parent_subactions.append((fullname, shortname,))
        formactions = {}
        for row in plpy.execute("select shortname, fullname from c_pytis_menu_actions where shortname like 'action/%' or shortname like 'print/%' order by shortname"):
            fullname = row['fullname']
            form_name = fullname[fullname.find('/', 7)+1:]
            form_name_formactions = formactions.get(form_name)
            if form_name_formactions is None:
                form_name_formactions = formactions[form_name] = []
            form_name_formactions.append((row['fullname'], row['shortname'],))
        actions = {}
        def add_row(fullname, shortname, menuid, position):
            if fullname[:4] == 'sub/':
                item_type = 'subf'
            elif fullname[:7] == 'action/':
                item_type = 'actf'
            elif fullname[:6] == 'print/':
                item_type = 'prnt'
            elif position.find('.') == -1:
                item_type = '----'
            elif menuid is None:
                item_type = 'spec'
            elif not fullname:
                item_type = 'sepa'
            elif fullname[:5] == 'menu/':
                item_type = 'menu'
            else:
                item_type = 'item'
            if menuid is None:
                menuid = 'NULL'
            plpy.execute(("insert into a_pytis_actions_structure (fullname, shortname, menuid, position, type) "
                          "values('%s', '%s', %s, '%s', '%s') ") %
                         (_pg_escape(fullname), _pg_escape(shortname), menuid, position, item_type,))
            actions[shortname] = True
        def add_formactions(shortname, position):
            formaction_list = formactions.get(shortname[5:], ())
            for i in range(len(formaction_list)):
                faction_fullname, faction_shortname = formaction_list[i]
                subposition = '%s.%02d' % (position, (i + 50),)
                add_row(faction_fullname, faction_shortname, None, subposition)
        for row in plpy.execute("select menuid, position, c_pytis_menu_actions.fullname, shortname "
                                "from e_pytis_menu, c_pytis_menu_actions "
                                "where e_pytis_menu.fullname = c_pytis_menu_actions.fullname "
                                "order by position"):
            menuid, position, shortname, fullname = row['menuid'], row['position'], row['shortname'], row['fullname']
            add_row(fullname, shortname, menuid, position)
            action_components = shortname.split('/')
            if action_components[0] == 'form' or action_components[0] == 'RUN_FORM':
                subaction_list = subactions.get(fullname, ())
                for i in range(len(subaction_list)):
                    sub_fullname, sub_shortname = subaction_list[i]
                    subposition = '%s.%02d' % (position, i,)
                    add_row(sub_fullname, sub_shortname, None, subposition)
                    add_formactions(sub_shortname, subposition)
                if not subaction_list:
                    add_formactions(shortname, position)
        position = '8.0001'
        add_row('label/1', 'label/1', None, '8')
        for row in plpy.execute("select fullname, shortname from c_pytis_menu_actions order by shortname"):
            fullname, shortname = row['fullname'], row['shortname']
            if shortname in actions:
                continue
            add_row(fullname, shortname, None, position)
            position_components = position.split('.')
            position = string.join(position_components[:-1] + ['%04d' % (int(position_components[-1]) + 1)], '.')
    finally:
        plpy.execute("select pg_advisory_unlock(%s)" % (lock_id,))
_plpy_function('pytis_update_actions_structure', (), TBoolean,
               body=pytis_update_actions_structure,
               depends=('a_pytis_actions_structure', 'e_pytis_menu', 'c_pytis_menu_actions', 'pytis_actions_lock_id',),)

function('pytis_multiform_spec', (TString,), TBoolean,
         body="""
select $1 not like ''sub/%'' and ($1 like ''%::%'' or $1 like ''%.Multi%'');
""")
 
sqltype('typ_preview_summary_rights',
        (C('shortname', TString),
         C('roleid', TString),
         C('rights', TString),
         C('columns', TString),
         C('purpose', TString),
         C('rights_show', TBoolean),
         C('rights_view', TBoolean),
         C('rights_insert', TBoolean),
         C('rights_update', TBoolean),
         C('rights_delete', TBoolean),
         C('rights_print', TBoolean),
         C('rights_export', TBoolean),
         C('rights_call', TBoolean),
         ))
function('pytis_view_summary_rights', (TString, TString, TBoolean, TBoolean,),
         RT('typ_preview_summary_rights', setof=True),
         body="""
select summary.shortname, summary.roleid, summary.rights, summary.columns,
       purposes.purpose,
       strpos(summary.rights, ''show'')::bool as rights_show,
       strpos(summary.rights, ''view'')::bool as rights_view,
       strpos(summary.rights, ''insert'')::bool as rights_insert,
       strpos(summary.rights, ''update'')::bool as rights_update,
       strpos(summary.rights, ''delete'')::bool as rights_delete,
       strpos(summary.rights, ''print'')::bool as rights_print,
       strpos(summary.rights, ''export'')::bool as rights_export,
       strpos(summary.rights, ''call'')::bool as rights_call
       from pytis_compute_summary_rights($1, $2, $3, $4, ''f'') as summary
            left outer join e_pytis_roles as roles on summary.roleid = roles.name
            left outer join c_pytis_role_purposes as purposes on roles.purposeid = purposes.purposeid;
""",
         grant=db_rights,
         depends=('typ_preview_summary_rights', 'pytis_compute_summary_rights', 'e_pytis_roles', 'c_pytis_role_purposes',))

sqltype('typ_preview_role_menu',
        (C('menuid', TInteger),
         C('title', TString),
         C('position', 'ltree'),
         C('position_nsub', 'bigint'),
         C('roleid', TString),
         C('rights', TString),
         C('rights_show', TBoolean),
         C('rights_view', TBoolean),
         C('rights_insert', TBoolean),
         C('rights_update', TBoolean),
         C('rights_delete', TBoolean),
         C('rights_print', TBoolean),
         C('rights_export', TBoolean),
         C('rights_call', TBoolean),
         ))
function('pytis_view_role_menu', (TString, TBoolean,), RT('typ_preview_role_menu', setof=True),
         body="""
select menu.menuid, menu.title, menu.position, menu.position_nsub, summary.roleid, summary.rights, 
       strpos(summary.rights, ''show'')::bool as rights_show,
       strpos(summary.rights, ''view'')::bool as rights_view,
       strpos(summary.rights, ''insert'')::bool as rights_insert,
       strpos(summary.rights, ''update'')::bool as rights_update,
       strpos(summary.rights, ''delete'')::bool as rights_delete,
       strpos(summary.rights, ''print'')::bool as rights_print,
       strpos(summary.rights, ''export'')::bool as rights_export,
       strpos(summary.rights, ''call'')::bool as rights_call
       from ev_pytis_menu as menu inner join pytis_compute_summary_rights(NULL, $1, $2, ''t'', ''t'') as summary
            on menu.shortname = summary.shortname;
""",
         grant=db_rights,
         depends=('typ_preview_role_menu', 'pytis_compute_summary_rights', 'e_pytis_roles', 'c_pytis_role_purposes',))

sqltype('typ_preview_extended_role_menu',
        (C('shortname', TString),
         C('position', 'ltree'),
         C('type', 'char(4)'),
         C('menuid', TInteger),
         C('next_position', 'ltree'),
         C('help', TString),
         C('hotkey', TString),
         C('locked', TBoolean),
         C('actiontype', TString),
         C('position_nsub', 'bigint'),
         C('title', TString),
         C('fullname', TString),
         C('roleid', TString),
         C('rights', TString),
         C('rights_show', TBoolean),
         C('rights_view', TBoolean),
         C('rights_insert', TBoolean),
         C('rights_update', TBoolean),
         C('rights_delete', TBoolean),
         C('rights_print', TBoolean),
         C('rights_export', TBoolean),
         C('rights_call', TBoolean),
         ))
function('pytis_view_extended_role_menu', (TString, TBoolean,), RT('typ_preview_extended_role_menu', setof=True),
         body="""
select structure.shortname, structure.position, structure.type,
       menu.menuid, menu.next_position, menu.help, menu.hotkey, menu.locked,
       atypes.description as actiontype,
       (select count(*)-1 from a_pytis_actions_structure where position <@ structure.position) as position_nsub,
       coalesce(menu.title, ''(''||actions.action_title||'')'') as title,
       structure.fullname, summary.roleid,
       summary.rights,
       strpos(summary.rights, ''show'')::bool as rights_show,
       strpos(summary.rights, ''view'')::bool as rights_view,
       strpos(summary.rights, ''insert'')::bool as rights_insert,
       strpos(summary.rights, ''update'')::bool as rights_update,
       strpos(summary.rights, ''delete'')::bool as rights_delete,
       strpos(summary.rights, ''print'')::bool as rights_print,
       strpos(summary.rights, ''export'')::bool as rights_export,
       strpos(summary.rights, ''call'')::bool as rights_call
from a_pytis_actions_structure as structure
     left outer join e_pytis_menu as menu on (structure.menuid = menu.menuid)
     inner join pytis_compute_summary_rights(NULL, $1, $2, ''t'', ''t'') as summary on (structure.shortname = summary.shortname)
     left outer join c_pytis_action_types as atypes on (structure.type = atypes.type)
     left outer join c_pytis_menu_actions as actions on (structure.fullname = actions.fullname)
     where pytis_multiform_spec(structure.fullname)
union
select structure.shortname, structure.position, structure.type,
       menu.menuid, menu.next_position, menu.help, menu.hotkey, menu.locked,
       atypes.description as actiontype,
       (select count(*)-1 from a_pytis_actions_structure where position <@ structure.position) as position_nsub,
       coalesce(menu.title, ''(''||actions.action_title||'')'') as title,
       structure.fullname, summary.roleid,
       summary.rights,
       strpos(summary.rights, ''show'')::bool as rights_show,
       strpos(summary.rights, ''view'')::bool as rights_view,
       strpos(summary.rights, ''insert'')::bool as rights_insert,
       strpos(summary.rights, ''update'')::bool as rights_update,
       strpos(summary.rights, ''delete'')::bool as rights_delete,
       strpos(summary.rights, ''print'')::bool as rights_print,
       strpos(summary.rights, ''export'')::bool as rights_export,
       strpos(summary.rights, ''call'')::bool as rights_call
from a_pytis_actions_structure as structure
     left outer join e_pytis_menu as menu on (structure.menuid = menu.menuid)
     inner join pytis_compute_summary_rights(NULL, $1, $2, ''f'', ''t'') as summary on (structure.shortname = summary.shortname)
     left outer join c_pytis_action_types as atypes on (structure.type = atypes.type)
     left outer join c_pytis_menu_actions as actions on (structure.fullname = actions.fullname)
     where not pytis_multiform_spec(structure.fullname);
""",
         grant=db_rights,
         depends=('typ_preview_extended_role_menu', 'a_pytis_actions_structure', 'e_pytis_menu',
                  'ev_pytis_valid_roles', 'pytis_compute_summary_rights', 'c_pytis_action_types',
                  'pytis_multiform_spec',))

sqltype('typ_preview_user_menu',
        (C('menuid', TInteger),
         C('name', TString),
         C('title', TString),
         C('position', 'ltree'),
         C('next_position', 'ltree'),         
         C('fullname', TString),
         C('help', TString),
         C('hotkey', TString),
         C('locked', TBoolean),
         ))
function('pytis_view_user_menu', (), RT('typ_preview_user_menu', setof=True),
         body="""
select menu.menuid, menu.name, menu.title, menu.position, menu.next_position, menu.fullname,
       menu.help, menu.hotkey, menu.locked
from ev_pytis_menu as menu
left outer join pytis_compute_summary_rights(NULL, pytis_user(), ''f'', ''t'', ''t'') as rights on (menu.shortname = rights.shortname)
where pytis_multiform_spec(menu.fullname) and rights.rights like ''%show%''
union
select menu.menuid, menu.name, menu.title, menu.position, menu.next_position, menu.fullname,
       menu.help, menu.hotkey, menu.locked
from ev_pytis_menu as menu
left outer join pytis_compute_summary_rights(NULL, pytis_user(), ''f'', ''f'', ''t'') as rights on (menu.shortname = rights.shortname)
where not pytis_multiform_spec(menu.fullname) and rights.rights like ''%show%''
union
select menu.menuid, menu.name, menu.title, menu.position, menu.next_position, menu.fullname,
       menu.help, menu.hotkey, menu.locked
from ev_pytis_menu as menu
where name is null and title is null;
""",
         grant=db_rights,
         depends=('typ_preview_user_menu', 'e_pytis_menu', 'pytis_compute_summary_rights', 'pytis_multiform_spec', 'pytis_user',))

sqltype('typ_preview_rights',
        (C('shortname', TString),
         C('rights', TString),
         C('columns', TString),
         ))
function('pytis_view_user_rights',  (), RT('typ_preview_rights', setof=True),
         body="""
select rights.shortname, rights.rights, rights.columns
from pytis_compute_summary_rights(NULL, pytis_user(), ''f'', ''f'', ''f'') as rights;
""",
         grant=db_rights,
         depends=('typ_preview_rights', 'pytis_compute_summary_rights', 'pytis_user',))

viewng('ev_pytis_user_roles',
       (SelectRelation('a_pytis_valid_role_members', alias='members', exclude_columns=('member'),
                       condition="members.member = pytis_user()"),
        SelectRelation('e_pytis_roles', alias='roles', exclude_columns=('*'),
                       condition="members.member = roles.name and roles.purposeid = 'user'", jointype=JoinType.INNER),
        ),
       insert=None,
       update=None,
       delete=None,
       grant=db_rights,
       depends=('e_pytis_roles', 'a_pytis_valid_role_members', 'pytis_user',))

sql_raw("""
create or replace view ev_pytis_colnames as select distinct shortname, colname
from e_pytis_action_rights where colname is not null;

create or replace rule ev_pytis_colnames_insert as on insert to ev_pytis_colnames do instead
insert into e_pytis_action_rights (shortname, roleid, rightid, colname, system, granted)
       values (new.shortname, '__pytis', '*', new.colname, False, False);
""",
        name='ev_pytis_colnames',
        depends=('e_pytis_action_rights',))

function('pytis_check_codebook_rights',  (TString, TString, TString, TBoolean,), RT('text', setof=True),
         body="""
(
 select roleid from pytis_compute_summary_rights(''form/''||$1, NULL, $4, ''f'', ''f'') where (rights like ''%insert%'' or rights like ''%update%'') and ('' ''||columns||'' '') like ''% $2 %''
 union
 (
  select roleid from pytis_compute_summary_rights(''form/''||$1, NULL, $4, ''f'', ''f'') where (rights like ''%insert%'' or rights like ''%update%'') and columns=''''
  except
  select roleid from pytis_compute_summary_rights(''form/''||$1, NULL, $4, ''f'', ''f'') where ('' ''||columns||'' '') like ''% $2 %''
 )
)
intersect
select roleid from pytis_compute_summary_rights(''form/''||$3, NULL, $4, ''f'', ''t'') where rights not like ''%view%'';
""",
         grant=db_rights,
         depends=('pytis_compute_summary_rights',))

sqltype('typ_changed_rights',
        (C('shortname', TString),
         C('roleid', TString),
         C('rights', TString),
         C('columns', TString),
         C('purpose', TString),
         C('rights_show', TBoolean),
         C('rights_view', TBoolean),
         C('rights_insert', TBoolean),
         C('rights_update', TBoolean),
         C('rights_delete', TBoolean),
         C('rights_print', TBoolean),
         C('rights_export', TBoolean),
         C('rights_call', TBoolean),
         C('change', TBoolean),
         ))
function('pytis_changed_rights',  (TString, TString, TBoolean,),
         RT('typ_changed_rights', setof=True),
         body="""
(
 select *, False as change from pytis_view_summary_rights($1, $2, ''f'', $3)
 except
 select *, False as change from pytis_view_summary_rights($1, $2, ''t'', $3)
)
union
(
 select *, True as change from pytis_view_summary_rights($1, $2, ''t'', $3)
 except
 select *, True as change from pytis_view_summary_rights($1, $2, ''f'', $3)
);
""",
         grant=db_rights,
         depends=('typ_changed_rights', 'pytis_view_summary_rights',))


def pytis_change_shortname(shortname, old_name, new_name):
    shortname, old_name, new_name = args
    if shortname is None:
        return shortname
    components = shortname.split('/')
    if (len(components) == 3 and
        components[0] in ('action', 'print',) and components[2] == old_name):
        components[2] = new_name
    elif (len(components) == 2 and
          components[0] == 'form' and components[1] == old_name):
        components[1] = new_name
    return '/'.join(components)
_plpy_function('pytis_change_shortname', (TString, TString, TString), TString,
               body=pytis_change_shortname)

def pytis_change_fullname(fullname, old_name, new_name):
    fullname, old_name, new_name = args
    if fullname is None:
        return fullname
    components = fullname.split('/')
    if (len(components) == 3 and
        components[0] in ('action', 'print',) and components[2] == old_name):
        components[2] = new_name
    elif (len(components) >= 3 and
          components[0] == 'form' and components[2] == old_name):
        components[2] = new_name
    elif (len(components) >= 5 and
          components[0] == 'sub' and components[4] == old_name):
        components[4] = new_name
    return '/'.join(components)        
_plpy_function('pytis_change_fullname', (TString, TString, TString), TString,
               body=pytis_change_fullname)

function('pytis_change_specification_name', (TString, TString), 'void',
         body="""
insert into e_pytis_disabled_dmp_triggers (id) values (''genmenu'');
update c_pytis_menu_actions set fullname=pytis_change_fullname(fullname, $1, $2), shortname=pytis_change_shortname(shortname, $1, $2) where shortname != pytis_change_shortname(shortname, $1, $2) or fullname != pytis_change_fullname(fullname, $1, $2);
update e_pytis_menu set fullname=pytis_change_fullname(fullname, $1, $2) where fullname != pytis_change_fullname(fullname, $1, $2);
update e_pytis_action_rights set shortname=pytis_change_shortname(shortname, $1, $2) where shortname != pytis_change_shortname(shortname, $1, $2);
update a_pytis_actions_structure set fullname=pytis_change_fullname(fullname, $1, $2), shortname=pytis_change_shortname(shortname, $1, $2) where shortname != pytis_change_shortname(shortname, $1, $2) or fullname != pytis_change_fullname(fullname, $1, $2);
delete from e_pytis_disabled_dmp_triggers where id=''genmenu'';
""",
         depends=('pytis_change_shortname', 'pytis_change_fullname', 'e_pytis_disabled_dmp_triggers',
                  'c_pytis_menu_actions', 'e_pytis_menu', 'e_pytis_action_rights',
                  'a_pytis_actions_structure',))
