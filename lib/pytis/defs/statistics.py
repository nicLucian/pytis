# -*- coding: utf-8 -*-

# Copyright (C) 2010, 2011, 2013, 2014 Brailcom, o.p.s.
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

import pytis.data
import pytis.extensions
import pytis.form
import pytis.presentation
from pytis.presentation import Binding, Field, Specification
import pytis.util

_ = pytis.util.translations('pytis-defs')

class FormShortStatistics(Specification):
    public = True
    table = 'ev_pytis_form_short_summary'
    title = _(u"Přehled používaných formulářů")
    fields = (
        Field('form', _(u"Jméno formuláře")),
        Field('class', _("Form Class")),
        Field('n_users', _(u"Počet uživatelů")),
        Field('n_open', _(u"Počet otevření")),
        Field('avg_start', _(u"Průměrná doba startu")),
        Field('last_used', _(u"Poslední spuštění")),
        )
    bindings = (Binding('users', _(u"Uživatelé"), 'statistics.FormUsers',
                        condition=(lambda row: pytis.data.AND(pytis.data.EQ('form', row['form']),
                                                              pytis.data.EQ('class', row['class'])))),
                )

class FormStatistics(Specification):
    public = True
    table = 'ev_pytis_form_summary'
    title = _(u"Podrobný přehled používaných formulářů")
    fields = (
        Field('form', _(u"Jméno formuláře")),
        Field('class', _("Form Class")),
        Field('info', _(u"Parametry formuláře")),
        Field('n_users', _(u"Počet uživatelů")),
        Field('n_open', _(u"Počet otevření")),
        Field('avg_start', _(u"Průměrná doba startu")),
        Field('last_used', _(u"Poslední spuštění")),
        )
    bindings = (Binding('users', _(u"Uživatelé"), 'statistics.FormUsers',
                        condition=(lambda row: pytis.data.AND(pytis.data.EQ('form', row['form']),
                                                              pytis.data.EQ('class', row['class']),
                                                              pytis.data.EQ('info', row['info'])))),
                )

class FormUsers(Specification):
    public = True
    table = 'ev_pytis_form_users'
    title = _(u"Uživatelé formuláře")
    fields = (
        Field('login', _(u"Login")),
        Field('form', _(u"Jméno formuláře")),
        Field('class', _("Form Class")),
        Field('info', _(u"Parametry formuláře")),
        Field('n_open', _(u"Počet otevření")),
        Field('last_used', _(u"Poslední spuštění")),
        )
    columns = ('login', 'info', 'n_open', 'last_used',)

class FormUserList(Specification):
    public = True
    table = 'ev_pytis_form_user_list'
    title = _(u"Uživatelé")
    fields = (
        Field('login', _(u"Login")),
        )
    bindings = (Binding('users', _(u"Formuláře"), 'statistics.FormUserStatistics',
                        condition=(lambda row: pytis.data.EQ('login', row['login']))),
                Binding('profiles', _("Profiles"), 'profiles.FormProfiles', 'username'),
                )

class FormUserStatistics(Specification):
    public = True
    table = 'ev_pytis_form_users'
    title = _(u"Formuláře uživatele")
    fields = (
        Field('login', _(u"Login")),
        Field('form', _(u"Jméno formuláře")),
        Field('class', _("Form Class")),
        Field('info', _(u"Parametry formuláře")),
        Field('n_open', _(u"Počet otevření")),
        Field('last_used', _(u"Poslední spuštění")),
        )
    columns = ('form', 'class', 'info', 'n_open', 'last_used',)

class FormUserStatisticsNoinfo(Specification):
    public = True
    table = 'ev_pytis_form_users_noinfo'
    title = _(u"Formuláře uživatele")
    fields = (
        Field('shortname', _("Action")),
        Field('login', _(u"Login")),
        Field('form', _(u"Jméno formuláře")),
        Field('class', _("Form Class")),
        Field('n_open', _(u"Počet otevření")),
        Field('last_used', _(u"Poslední spuštění")),
        )
    columns = ('login', 'class', 'n_open', 'last_used',)
    
    def on_new_record(self, prefill=None, transaction=None):
        try:
            pytis.form.run_form(pytis.form.PopupEditForm, 'Nastaveni.BvUsersCfg',
                                select_row=pytis.extensions.cfg_param('id', cfgspec='Nastaveni.BvUsersCfg'))
        except pytis.util.ResolverError:
            pytis.form.run_dialog(pytis.form.Warning, _(u"Tato databáze neobsahuje uživatelskou konfiguraci"))
