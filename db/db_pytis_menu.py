# -*- coding: iso-8859-2 -*-

"""Gensql definitions for dynamic application menus and access rights."""

db_rights = globals().get('Gall_pytis', None)
if not db_rights:
    raise ProgramError('No rights specified! Please define Gpytis_menu')

### Roles

_std_table_nolog('c_pytis_role_purposes',
                 (P('purposeid', 'char(4)'),
                  C('purpose', 'varchar(32)', constraints=('unique', 'not null',)),),
                 """There are three kinds of roles:
1. Menu and access administrator roles.  Definitions of these roles may be changed
   only by the database administrators.
2. Roles corresponding to system accounts (login roles).
3. Pure application roles.
""",
                 init_values=(("'admn'", "'Spr�vcovsk�'",),
                              ("'user'", "'U�ivatelsk�'",),
                              ("'appl'", "'Aplika�n�'",),)
            )

_std_table('e_pytis_roles',
           (P('name', TUser),
            C('description', 'varchar(64)'),
            C('purposeid', 'char(4)', constraints=('not null',), default="'appl'",
              references='c_pytis_role_purposes'),
            C('deleted', TDate),),
            """Application user roles.""",
           init_values=(("'admin_roles'", "'Administr�tor rol�'", "'admn'", 'NULL',),
                        ("'admin_menu'", "'Administr�tor menu'", "'admn'", 'NULL',),
                        ("'admin'", "'Administr�tor rol� a menu'", "'admn'", 'NULL',),
                        ),
           depends=('c_pytis_role_purposes',))
def e_pytis_roles_trigger():
    class Roles(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_roles(self):
            plpy.execute("select pytis_update_transitive_roles()")
        def _update_rights(self, roleid):
            menus = plpy.execute("select menuid, name from e_pytis_menu")
            safe_roleid = self._pg_escape(roleid)
            for row in menus:
                plpy.execute("select pytis_compute_rights('%s', '%s', '%s')" %
                             (row['menuid'], safe_roleid, self._pg_escape(row['name'] or ''),))
        def _do_after_insert(self):
            role = self._pg_escape(self._new['name'])
            plpy.execute("insert into a_pytis_valid_role_members(roleid, member) values ('%s', '%s')" %
                         (role, role,))
            self._update_rights(self._new['name'])
        def _do_after_update(self):
            if self._new['deleted'] != self._old['deleted']:
                self._update_roles()
                if self._new['deleted']:
                    condition = ("roleid = '%s' or roleid = '%s'" %
                                 (self._pg_escape(self._old['name']), self._pg_escape(self._new['name']),))
                    plpy.execute("delete from a_pytis_computed_rights where %s" % (condition,))
                    plpy.execute("delete from a_pytis_computed_summary_rights where %s" % (condition,))
                else:
                    self._update_rights(self._new['name'])
        def _do_after_delete(self):
            self._update_roles()
    roles = Roles(TD)
    return roles.do_trigger()
_trigger_function('e_pytis_roles_trigger', body=e_pytis_roles_trigger,
                  doc="Updates total role memberships.",
                  depends=('e_pytis_roles', 'a_pytis_valid_role_members', 'pytis_update_transitive_roles',))
sql_raw("""
create trigger e_pytis_roles_insert_after after insert on e_pytis_roles
for each row execute procedure e_pytis_roles_trigger();
create trigger e_pytis_roles_update_after after update or delete on e_pytis_roles
for each statement execute procedure e_pytis_roles_trigger();
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
       depends=('e_pytis_roles', 'c_pytis_role_purposes',)
       )

viewng('ev_pytis_user_roles',
       (SelectRelation('e_pytis_roles', alias='main',
                       condition=("(main.deleted is null or main.deleted > now()) and "
                                  "main.purposeid = 'user' and "
                                  "main.name = session_user")),
        SelectRelation('pg_roles', alias='roles', key_column='pg_roles', exclude_columns=('*',),
                       condition=("main.name = roles.rolname and "
                                  "pg_has_role(roles.rolname, 'member')"),
                       jointype=JoinType.INNER),
        ),
       insert_order=('e_pytis_roles',),
       update_order=('e_pytis_roles',),
       delete_order=('e_pytis_roles',),
       grant=db_rights,
       depends=('e_pytis_roles',)
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
Entries in this table define `member's of each `roleid'.
""",
           init_values=(('-1', "'admin_roles'", "'admin'",),
                        ('-2', "'admin_menu'", "'admin'",),
                        ),
           depends=('e_pytis_roles',))
def e_pytis_role_members_trigger():
    class Roles(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_roles(self):
            plpy.execute("select pytis_update_transitive_roles()")
        def _update_rights(self, changed_role):
            menus = plpy.execute("select menuid, name from e_pytis_menu")
            q = ("select member from a_pytis_valid_role_members where roleid = '%s'" %
                 (self._pg_escape(changed_role),))
            roles = [row['member'] for row in plpy.execute(q)]
            for roleid in roles:
                safe_roleid = self._pg_escape(roleid)
                for row in menus:
                    plpy.execute("select pytis_compute_rights('%s', '%s', '%s')" %
                                 (row['menuid'], safe_roleid, self._pg_escape(row['name'] or ''),))            
        def _do_after_insert(self):
            self._update_roles()
            self._update_rights(self._new['member'])
        def _do_after_update(self):
            self._update_roles()
            self._update_rights(self._new['member'])
            if self._new['member'] != self._old['member']:
                self._update_rights(self._old['member'])                
        def _do_after_delete(self):
            self._update_roles()
            self._update_rights(self._old['member'])                
    roles = Roles(TD)
    return roles.do_trigger()
_trigger_function('e_pytis_role_members_trigger', body=e_pytis_role_members_trigger,
                  doc="Updates total role memberships.",
                  depends=('e_pytis_role_members', 'a_pytis_valid_role_members', 'pytis_update_transitive_roles',))
sql_raw("""
create trigger e_pytis_role_members_all_after after insert or update or delete on e_pytis_role_members
for each statement execute procedure e_pytis_role_members_trigger();
""",
        name='e_pytis_role_members_triggers',
        depends=('e_pytis_role_members_trigger',))

viewng('ev_pytis_valid_role_members',
       (SelectRelation('e_pytis_role_members', alias='main'),
        SelectRelation('ev_pytis_valid_roles', alias='roles1', exclude_columns=('purpose',),
                       condition='roles1.name = main.roleid', jointype=JoinType.INNER),
        SelectRelation('ev_pytis_valid_roles', alias='roles2', exclude_columns=('purpose',),
                       column_aliases=(('name', 'mname',),
                                       ('description', 'mdescription',),
                                       ('purposeid', 'mpurposeid',),
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

### Actions

_std_table_nolog('c_pytis_menu_actions',
                 (P('name', TString),
                  C('shortname', TString, constraints=('not null',)),
                  C('description', TString),
                  ),
                 """List of available (pre-defined and visible) application actions."""
                 )

### Menus

_std_table('e_pytis_menu',
           (P('menuid', TSerial),
            C('name', TString, constraints=('unique',),
              doc="Unique identifiers of terminal menu items.  NULL for non-terminal items and separators."),
            C('title', 'varchar(64)',
              doc='User title of the item. If NULL then it is a separator.'),
            C('parent', TInteger, references='e_pytis_menu',
              doc="Parent menu item, NULL for top level items."),
            C('position', TInteger, constraints=('not null',),
              doc=("Order of the item within the given submenu. "
                   "Lower numbers put the item higher. "
                   "No two items in the same submenu should have the same order number; "
                   "if they do, their mutual order is undefined.")),
            C('fullposition', TString,
              doc=("Full position including parent items. "
                   "Lexicographical ordering of all menu items. ")),
            C('indentation', 'varchar(8)',
              doc="Indentation of the menu item in the menu structure"),
            C('action', TString, references='c_pytis_menu_actions',
              doc=("Application action assigned to the menu item."
                   "Menu items bound to submenus should have this value NULL; "
                   "if they do not, the assigned action is ignored.")),
            ),
           """Menu structure definition.""",
           depends=('c_pytis_menu_actions',))

def e_pytis_menu_trigger():
    class Menu(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _do_before_insert(self, old=None):
            parent_id = self._new['parent']
            if not parent_id:
                return
            data = plpy.execute("select indentation, fullposition from e_pytis_menu where menuid = %s" %
                                (parent_id,))
            parent = data[0]
            self._new['indentation'] = parent['indentation'] + '   '
            self._new['fullposition'] = parent['fullposition'] + str(self._new['position'])
            if not self._new['name'] and self._new['title'] and (old is None or not old['title']):
                # New non-terminal menu item
                self._new['action'] = action = 'menu/' + str(self._new['menuid'])
                plpy.execute(("insert into c_pytis_menu_actions (name, shortname, description) "
                              "values ('%s', '%s', '%s')") % (action, action, self._pg_escape("Menu '%s'" % (self._new['title'])),))
            self._return_code = self._RETURN_CODE_MODYFY
        def _update_rights(self, record):
            menuid = record['menuid']
            name = record['name']
            q = "select name from ev_pytis_valid_roles"
            roles = [row['name'] for row in plpy.execute(q)]
            for roleid in roles:
                plpy.execute("select pytis_compute_rights('%s', '%s', '%s')" %
                             (menuid, self._pg_escape(roleid), self._pg_escape(name or ''),))
        def _do_after_insert(self):
            self._update_rights(self._new)
        def _do_before_update(self):
            self._do_before_insert(old=self._old)
        def _do_after_update(self):
            plpy.execute("update e_pytis_menu set parent=parent where parent=%s" %
                         (self._new['menuid'],))
            if not self._new['name'] and self._old['title'] and not self._new['title']:
                # Non-terminal item changed to separator
                plpy.execute("delete from c_pytis_actions where name = '%s'" % (self._old['action'],))
                plpy.execute("delete from e_pytis_action_rights where action = '%s'" % (self._old['action'],))
            if self._new['parent'] != self._old['parent']:
                self._update_rights(self._new)
        def _do_before_delete(self):
            data = plpy.execute("select * from e_pytis_menu where parent=%s" %
                                (self._old['menuid'],))
            if data:
                self._return_code = self._RETURN_CODE_SKIP
        def _do_after_delete(self):
            if not self._old['name'] and self._old['title']:
                # Non-terminal menu item
                plpy.execute("delete from c_pytis_actions where name = '%s'" % (self._old['action'],))
                plpy.execute("delete from e_pytis_action_rights where action = '%s'" % (self._old['action'],))
    menu = Menu(TD)
    return menu.do_trigger()
_trigger_function('e_pytis_menu_trigger', body=e_pytis_menu_trigger,
                  doc="Updates indentations and fullpositions",
                  depends=('e_pytis_menu',))
sql_raw("""
create trigger e_pytis_menu_all_before before insert or update or delete on e_pytis_menu
for each row execute procedure e_pytis_menu_trigger();
create trigger e_pytis_menu_all_after after insert or update or delete on e_pytis_menu
for each row execute procedure e_pytis_menu_trigger();
""",
        name='e_pytis_menu_triggers',
        depends=('e_pytis_menu_trigger',))

viewng('ev_pytis_menu',
       (SelectRelation('e_pytis_menu', alias='main', exclude_columns=('action',)),
        SelectRelation('c_pytis_menu_actions', alias='actions', exclude_columns=('description',),
                       column_aliases=(('name', 'action',),),
                       condition='main.action = actions.name', jointype=JoinType.LEFT_OUTER),
        ),
       include_columns=(V(None, 'ititle', "main.indentation || ' ' || main.title"),),
       insert_order=('e_pytis_menu',),
       update_order=('e_pytis_menu',),
       delete_order=('e_pytis_menu',),
       grant=db_rights,
       depends=('e_pytis_menu', 'c_pytis_menu_actions',)
       )

viewng('ev_pytis_menu_parents',
       (SelectRelation('ev_pytis_menu', alias='main',
                       condition='main.name is null and main.title is not null'),),
       insert_order=('e_pytis_menu',),
       update_order=('e_pytis_menu',),
       delete_order=('e_pytis_menu',),
       grant=db_rights,
       depends=('ev_pytis_menu',)
       )

### Access rights

_std_table_nolog('c_pytis_access_rights',
                 (P('rightid', 'varchar(8)'),
                  C('description', 'varchar(32)', constraints=('not null',)),
                  ),
                 """Available rights.  Not all rights make sense for all actions and menus.""",
                 init_values=(("'show'", _("'Viditelnost polo�ek menu'"),),
                              ("'view'", _("'Prohl��en� existuj�c�ch z�znam�'"),),
                              ("'insert'", _("'Vkl�d�n� nov�ch z�znam�'"),),
                              ("'update'", _("'Editace existuj�c�ch z�znam�'"),),
                              ("'delete'", _("'Maz�n� z�znam�'"),),
                              ("'print'", _("'Tisky'"),),
                              ("'export'", _("'Exporty'"),),
                              ("'call'", _("'Spou�t�n� aplika�n�ch procedur'"),),
                              ))

_std_table('e_pytis_action_rights',
           (P('id', TSerial,
              doc="Just to make logging happy"),
            C('action', TString, constraints=('not null',)),
            C('roleid', TUser, references='e_pytis_roles', constraints=('not null',)),
            C('rightid', 'varchar(8)', references='c_pytis_access_rights', constraints=('not null',)),
            C('colname', TUser),
            C('system', TBoolean, constraints=('not null',), default=False,
              doc="Iff true, this is a system (noneditable) permission."),
            C('granted', TBoolean, constraints=('not null',), default=True,
              doc="If true the right is granted, otherwise it is denied; system rights are always granted."),
            ),
           """Assignments of access rights to actions.

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
           depends=('c_pytis_menu_actions', 'e_pytis_roles', 'c_pytis_access_rights',)
           )
def e_pytis_action_rights_trigger():
    class Rights(BaseTriggerObject):
        def _pg_escape(self, val):
            return str(val).replace("'", "''")
        def _update_rights(self, action, roleid):
            menus = plpy.execute("select menuid, name from e_pytis_menu where pytis_matching_actions(action, '%s')" %
                                 (action,))
            safe_roleid = self._pg_escape(roleid)
            for row in menus:
                plpy.execute("select pytis_compute_rights('%s', '%s', '%s')" %
                             (row['menuid'], safe_roleid, self._pg_escape(row['name'] or ''),))
        def _do_after_insert(self):
            self._update_rights(self._new['action'], self._new['roleid'])
        def _do_after_update(self):
            self._update_rights(self._old['action'], self._old['roleid'])
            self._update_rights(self._new['action'], self._new['roleid'])
        def _do_after_delete(self):
            self._update_rights(self._old['action'], self._old['roleid'])
    rights = Rights(TD)
    return rights.do_trigger()
_trigger_function('e_pytis_action_rights_trigger', body=e_pytis_action_rights_trigger,
                  doc="Updates summary access rights.",
                  depends=('e_pytis_action_rights', 'e_pytis_menu', 'pytis_compute_rights', 'pytis_matching_actions',))
sql_raw("""
create trigger e_pytis_action_rights_all_after after insert or update or delete on e_pytis_action_rights
for each row execute procedure e_pytis_action_rights_trigger();
""",
        name='e_pytis_action_rights_triggers',
        depends=('e_pytis_action_rights_trigger',))

def pytis_matching_actions(complex_action, simple_action):
    complex_action = args[0]
    simple_action = args[1]
    if complex_action is None:
        return False
    components = complex_action.split('/')
    if components[0] == 'form':
        last_components = components[-1].split('::')
        if len(last_components) == 2:
            import string
            prefix = string.join(components[:-1], '/')
            return ((prefix + last_components[0]) == simple_action or
                    (prefix + last_components[1]) == simple_action)
    return complex_action == simple_action
_plpy_function('pytis_matching_actions', (TString, TString), TBoolean,
               body=pytis_matching_actions)
    
viewng('ev_pytis_menu_rights',
       (SelectRelation('e_pytis_menu', alias='menu', exclude_columns=('name', 'parent', 'position', 'fullposition', 'indentation', 'action',)),
        SelectRelation('c_pytis_menu_actions', alias='actions', exclude_columns=('*',),
                       condition='pytis_matching_actions(menu.action, actions.name)', jointype=JoinType.INNER),
        SelectRelation('e_pytis_action_rights', alias='rights', exclude_columns=(),
                       condition='actions.shortname = rights.action', jointype=JoinType.INNER,
                       column_aliases=(('action', 'shortname',),)),
        ),
       insert_order=('e_pytis_action_rights',),
       update_order=('e_pytis_action_rights',),
       delete_order=('e_pytis_action_rights',),
       grant=db_rights,
       depends=('e_pytis_menu', 'c_pytis_menu_actions', 'e_pytis_action_rights',)
       )

def pytis_compute_rights(menuid, roleid, name):
    menuid = args[0]
    roleid = args[1]
    name = args[2]
    def _pg_escape(val):
        return str(val).replace("'", "''")
    safe_roleid = _pg_escape(roleid)
    def compute(menuid, name):
        default_condition = ("menuid = '%s' and roleid in (select roleid from a_pytis_valid_role_members where member='%s')"
                             % (menuid, safe_roleid,))
        condition = [default_condition]
        def execute(query):
            return [row['rightid'] for row in plpy.execute(query % condition[0])]
        if name:
            max_rights = execute("select rightid from ev_pytis_menu_rights where "
                                 "system = 'T' and %s")
        else:
            max_rights = None
        allowed_rights = execute(("select rightid from ev_pytis_menu_rights where "
                                  "system = 'F' and granted = 'T' and %s"))
        forbidden_rights = execute(("select rightid from ev_pytis_menu_rights where "
                                    "system = 'F' and granted = 'F' and %s"))
        parent_menuid = menuid
        while True:
            parents = plpy.execute("select parent from e_pytis_menu where menuid = '%s'" %
                                   (parent_menuid,))
            parent_menuid = parents[0]['parent']
            if parent_menuid is None:
                # Root menu item
                break
            condition[0] = "menuid = '%s' and roleid = '%s'" % (parent_menuid, roleid,)
            query = ("select rightid from ev_pytis_menu_rights where "
                     "system = 'F' and granted = 'T' and %s")
            allowed_rights += [right for right in execute(query)
                               if right not in allowed_rights and right not in forbidden_rights]
            query = ("select rightid from ev_pytis_menu_rights where "
                     "system = 'F' and granted = 'F' and %s")
            forbidden_rights += [right for right in execute(query)
                                 if right not in allowed_rights and right not in forbidden_rights]
        if max_rights is None:
            max_rights = allowed_rights
        rights = [right for right in max_rights if right not in forbidden_rights]
        if 'show' not in forbidden_rights:
            rights.append('show')
        rights.sort()
        old_rights = [row['rightid'] for row in
                      plpy.execute("select rightid from a_pytis_computed_rights where %s" %
                                   (default_condition,))]
        old_rights.sort()
        different = (old_rights != rights)
        if different:
            plpy.execute("delete from a_pytis_computed_rights where %s" % (default_condition,))
            for r in rights:
                plpy.execute("insert into a_pytis_computed_rights (menuid, roleid, rightid) values (%s, '%s', '%s')" %
                             (menuid, safe_roleid, r,))
            plpy.execute("delete from a_pytis_computed_summary_rights where %s" % (default_condition,))
            plpy.execute(("insert into a_pytis_computed_summary_rights (menuid, roleid, rights) "
                          "values (%s, '%s', pytis_summary_rights(%s, '%s'))")
                         % (menuid, safe_roleid, menuid, safe_roleid,))
            submenus = plpy.execute("select menuid, name from e_pytis_menu where parent = '%s'" %
                                    (menuid,))
        else:
            submenus = []
        return submenus
    menus = [dict(menuid=menuid, name=name)]
    while menus:
        row = menus.pop()
        menus += compute(row['menuid'], row['name'])
    return True
_plpy_function('pytis_compute_rights', (TInteger, TUser, TString), TBoolean,
               body=pytis_compute_rights,
               depends=('e_pytis_action_rights', 'a_pytis_computed_rights', 'a_pytis_computed_summary_rights', 'pytis_summary_rights',),)

def pytis_summary_rights(menuid, roleid):
    menuid = args[0]
    roleid = args[1]
    def _pg_escape(val):
        return str(val).replace("'", "''")
    q = ("select distinct rightid from a_pytis_computed_rights where menuid = '%s' and roleid = '%s'"
         % (menuid, _pg_escape(roleid),))
    rights = [row['rightid'] for row in plpy.execute(q)]
    if rights:
        import string
        formatted_rights = string.join(rights, ' ')
    else:
        formatted_rights = None
    return formatted_rights    
_plpy_function('pytis_summary_rights', (TInteger, TUser), TString,
               body=pytis_summary_rights,
               depends=('a_pytis_computed_rights',),)

_std_table_nolog('a_pytis_computed_rights',
                 (C('menuid', TInteger, constraints=('not null',), references='e_pytis_menu on delete cascade on update cascade'),
                  C('roleid', TString, constraints=('not null',), references='e_pytis_roles on delete cascade on update cascade'),
                  C('rightid', 'varchar(8)', constraints=('not null',), references='c_pytis_access_rights on delete cascade on update cascade'),
                  ),
                 """Precomputed summary access rights line by line.
This table is modified only by triggers.
""",
                 depends=('e_pytis_menu', 'e_pytis_roles', 'c_pytis_access_rights',))

_std_table_nolog('a_pytis_computed_summary_rights',
                 (C('menuid', TInteger, constraints=('not null',), references='e_pytis_menu on delete cascade on update cascade'),
                  C('roleid', TString, constraints=('not null',), references='e_pytis_roles on delete cascade on update cascade'),
                  C('rights', TString, constraints=('not null',)),
                  ),
                 """Precomputed summary access rights as a single line string.
This table is modified only by triggers.
""",
                 depends=('e_pytis_menu', 'e_pytis_roles',))

viewng('ev_pytis_summary_rights_raw',
       (SelectRelation('e_pytis_menu', alias='menu', exclude_columns=('name', 'parent', 'position', 'fullposition', 'indentation', 'action',)),
        SelectRelation('ev_pytis_valid_roles', alias='roles', exclude_columns=('description', 'purposeid', 'deleted',),
                       jointype=JoinType.CROSS),
        SelectRelation('a_pytis_computed_summary_rights', alias='summary', exclude_columns=('menuid', 'roleid',),
                       condition="menu.menuid = summary.menuid and roles.name = summary.roleid" , jointype=JoinType.INNER),
        ),
       insert=None,
       update=None,
       delete=None,
       grant=db_rights,
       depends=('e_pytis_menu', 'ev_pytis_valid_roles', 'pytis_compute_rights', 'a_pytis_computed_summary_rights',)
       )

viewng('ev_pytis_summary_rights',
       (SelectRelation('ev_pytis_summary_rights_raw', alias='rights', condition='rights is not null'),),
       insert=None,
       update=None,
       delete=None,
       grant=db_rights,
       depends=('ev_pytis_summary_rights_raw',)
       )

viewng('ev_pytis_role_menu_raw',
       (SelectRelation('ev_pytis_menu', alias='menu', exclude_columns=('name', 'parent', 'position', 'indentation', 'action',)),
        SelectRelation('ev_pytis_valid_roles', alias='roles', exclude_columns=('description', 'purposeid', 'deleted',),
                       jointype=JoinType.CROSS,
                       column_aliases=(('name', 'roleid',),),
                       ),
        SelectRelation('a_pytis_computed_summary_rights', alias='summary', exclude_columns=('menuid', 'roleid',),
                       condition="menu.menuid = summary.menuid and roles.name = summary.roleid" , jointype=JoinType.INNER),
        ),
       insert=None,
       update=None,
       delete=None,
       grant=db_rights,
       depends=('ev_pytis_menu', 'ev_pytis_valid_roles', 'pytis_compute_rights', 'a_pytis_computed_summary_rights',)
       )

viewng('ev_pytis_role_menu',
       (SelectRelation('ev_pytis_role_menu_raw', alias='menu', condition="rights like '%show%'"),),
       insert=None,
       update=None,
       delete=None,
       grant=db_rights,
       depends=('ev_pytis_role_menu_raw',)
       )
