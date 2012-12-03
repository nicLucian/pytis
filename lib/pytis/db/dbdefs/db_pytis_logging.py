# -*- coding: utf-8

import sqlalchemy
import pytis.extensions.gensqlalchemy as sql
import pytis.data
import dbdefs as db

class EPytisActionLog(sql.SQLTable):
    """Pytis user actions log."""
    name = 'e_pytis_action_log'
    fields = (
              sql.PrimaryColumn('id', pytis.data.Serial(not_null=False)),
              sql.Column('timestamp', pytis.data.DateTime(not_null=True)),
              sql.Column('username', pytis.data.Name(not_null=True)),
              sql.Column('spec_name', pytis.data.String(not_null=True)),
              sql.Column('form_name', pytis.data.String(not_null=True)),
              sql.Column('action', pytis.data.String(not_null=True)),
              sql.Column('info', pytis.data.String(not_null=False)),
             )
    inherits = (db.XChanges,)
    with_oids = True
    depends_on = ()
    access_rights = db.default_access_rights.value(globals())
