# -*- coding: utf-8

import sqlalchemy
import pytis.extensions.gensqlalchemy as sql
import pytis.data
import dbdefs as db

class EPytisConfig(sql.SQLTable):
    """Pytis application configuration storage."""
    name = 'e_pytis_config'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('username', pytis.data.Name(not_null=True), unique=True),
              sql.Column('pickle', pytis.data.String(not_null=True)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())

class EPytisFormSettings(sql.SQLTable):
    """Storage of pytis profile independent form settings."""
    name = 'e_pytis_form_settings'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('username', pytis.data.Name(not_null=True)),
              sql.Column('spec_name', pytis.data.String(not_null=True)),
              sql.Column('form_name', pytis.data.String(not_null=True)),
              sql.Column('pickle', pytis.data.String(not_null=True)),
              sql.Column('dump', pytis.data.String(not_null=False)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    unique = (('username', 'spec_name', 'form_name',),)
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())

class EPytisFormProfileBase(sql.SQLTable):
    """Pytis form configuration storage."""
    name = 'e_pytis_form_profile_base'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('username', pytis.data.Name(not_null=True)),
              sql.Column('spec_name', pytis.data.String(not_null=True)),
              sql.Column('profile_id', pytis.data.String(not_null=True)),
              sql.Column('title', pytis.data.String(not_null=True)),
              sql.Column('pickle', pytis.data.String(not_null=True)),
              sql.Column('dump', pytis.data.String(not_null=False)),
              sql.Column('errors', pytis.data.String(not_null=False)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    unique = (('username', 'spec_name', 'profile_id',),)
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())

class EPytisFormProfileParams(sql.SQLTable):
    """Pytis form profile form type specific parameters."""
    name = 'e_pytis_form_profile_params'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('username', pytis.data.Name(not_null=True)),
              sql.Column('spec_name', pytis.data.String(not_null=True)),
              sql.Column('form_name', pytis.data.String(not_null=True)),
              sql.Column('profile_id', pytis.data.String(not_null=True)),
              sql.Column('pickle', pytis.data.String(not_null=True)),
              sql.Column('dump', pytis.data.String(not_null=False)),
              sql.Column('errors', pytis.data.String(not_null=False)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    unique = (('username', 'spec_name', 'form_name', 'profile_id',),)
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())

class EvPytisFormProfiles(sql.SQLView):
    """Pytis profiles."""
    name = 'ev_pytis_form_profiles'
    @classmethod
    def query(cls):
        profile = sql.t.EPytisFormProfileBase.alias('profile')
        params = sql.t.EPytisFormProfileParams.alias('params')
        return sqlalchemy.select(
            cls._exclude(profile, 'id', 'username', 'spec_name', 'profile_id', 'pickle', 'dump', 'errors') +
            cls._exclude(params, 'id', 'pickle', 'dump', 'errors') +
            [sql.gL("profile.id||'.'||params.id").label('id'),
             sql.gL("'form/'|| params.form_name ||'/'|| profile.spec_name ||'//'").label('fullname'),
             sql.gL("case when profile.errors is not null and params.errors is not null then profile.errors ||'\n'||params.errors else coalesce(profile.errors, params.errors) end").label('errors'),
             sql.gL("case when profile.dump is not null and params.dump is not null then profile.dump ||'\n'||params.dump else coalesce(profile.dump, params.dump) end").label('dump'),
             profile.c.pickle.label('pickled_filter'),
             params.c.pickle.label('pickled_params')],
            from_obj=[profile.join(params, sql.gR('profile.username = params.username and profile.spec_name = params.spec_name and profile.profile_id = params.profile_id'))]
            )

    def on_delete(self):
        return ("(delete from e_pytis_form_profile_base where id = split_part(old.id, '.', 1)::int;delete from e_pytis_form_profile_params where id = split_part(old.id, '.', 2)::int;)",)
    depends_on = (EPytisFormProfileBase, EPytisFormProfileParams,)
    access_rights = db.default_access_rights.value(globals())

class CopyUserProfile(sql.SQLFunction):
    """Zkopíruje profil z ev_pytis_form_profiles jinému uživateli."""
    name = 'copy_user_profile'
    arguments = (sql.Column('profile_id', pytis.data.String()),
                 sql.Column('username', pytis.data.String()),)
    result_type = pytis.data.String()
    multirow = False
    stability = 'VOLATILE'
    depends_on = (EvPytisFormProfiles,)
    access_rights = ()

    def body(self):
        return """with newid as (
select '_user_profile_' || (coalesce(max(split_part(profile_id, '_',4)::int),0) + 1)::text as profile_id
   from ev_pytis_form_profiles p
   where p.username = $2
   and p.spec_name = (select spec_name from ev_pytis_form_profiles where id = $1 limit 1)
   ), profiles as
  (insert into e_pytis_form_profile_base 
   (username, spec_name, profile_id, title, pickle)
    select $2 as username, spec_name, newid.profile_id, title, pickled_filter
     from ev_pytis_form_profiles profiles, newid
    where id = $1 returning *), params as
     (insert into e_pytis_form_profile_params
      (username, spec_name, profile_id, form_name, pickle)
       select profiles.username, profiles.spec_name, newid.profile_id, params.form_name,
              params.pickled_params
         from ev_pytis_form_profiles params, newid, profiles
        where params.id = $1 returning *)
select profiles.id || '.' || params.id from profiles, params
"""

class EPytisAggregatedViews(sql.SQLTable):
    """Pytis aggregated views storage."""
    name = 'e_pytis_aggregated_views'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('username', pytis.data.Name(not_null=True)),
              sql.Column('spec_name', pytis.data.String(not_null=True)),
              sql.Column('aggregated_view_id', pytis.data.String(not_null=True)),
              sql.Column('title', pytis.data.String(not_null=True)),
              sql.Column('pickle', pytis.data.String(not_null=True)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    unique = (('username', 'spec_name', 'aggregated_view_id',),)
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())
