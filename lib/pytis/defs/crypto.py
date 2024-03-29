# -*- coding: utf-8 -*-

# Copyright (C) 2014, 2015 Brailcom, o.p.s.
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

import copy

import pytis.data
import pytis.extensions
from pytis.presentation import Specification, Field, Binding
from pytis.util import rsa_encrypt, translations
from pytis.dbdefs import db_pytis_crypto

_ = translations('pytis')

class NewAdminPasswd(Specification):
    public = True

    data_cls = pytis.data.RestrictedMemData
    title = _(u"Změna administrátorského hesla")

    def fields(self):
        return (
            Field('old_password', _(u'Stávající heslo'), width=20,
                  type=pytis.data.Password, md5=False, verify=False),
            Field('new_password', _(u'Nové heslo'), width=20,
                  type=pytis.data.Password, maxlen=32, minlen=8, md5=False,
                  strength=self._check_strength),
        )

    def _check_strength(self, passwd):
        lower = upper = digits = False
        for char in passwd:
            if char.isalpha() and char.islower():
                lower = True
            elif char.isalpha() and char.isupper():
                upper = True
            elif char.isdigit():
                digits = True
        if not (lower and upper and digits):
            return _(u"Použijte, prosím, kombinaci malých a velkých znaků a číslic.")


class CryptoAreas(Specification):
    public = True
    table = db_pytis_crypto.CPytisCryptoNames
    title = _(u"Šifrovací oblasti")
    sorting = (('name', pytis.data.ASCENDENT,),)
    bindings = (Binding('users', _(u"Uživatelé"), 'crypto.Users', binding_column='name'),)

    def actions(self):
        return (pytis.presentation.Action('change_password', _(u"Změnit heslo administrátora"),
                                          self._change_admin_password),)

    def _change_admin_password(self, row):
        area = row['name'].value()
        if not area:
            return
        db_key = pytis.extensions.dbfunction('pytis_crypto_db_key',
                                             ('key_name_', pytis.data.sval('pytis'),))
        import config
        connection_data = config.dbconnection
        key_id, key = pytis.extensions.crypto_admin_key(area, 'admin', connection_data)
        if not key_id or not key:
            pytis.form.run_dialog(pytis.form.Error,
                                  _(u"Nebyl nalezen klíč administrátora pro tuto oblast"))
            return
        row = pytis.form.new_record("crypto.NewAdminPasswd", multi_insert=False)
        if not row:
            return
        old_password = row["old_password"].value()
        if not pytis.extensions.check_crypto_password(key, old_password, connection_data):
            pytis.form.run_dialog(pytis.form.Error, _(u"Chybné heslo"))
        encrypted_old_password = rsa_encrypt(db_key, old_password)
        new_password = row["new_password"].value()
        encrypted_new_password = rsa_encrypt(db_key, new_password)
        function = pytis.data.DBFunctionDefault('pytis_crypto_change_password', connection_data)
        row = pytis.data.Row((('id_', key_id,),
                              ('old_psw', pytis.data.sval(encrypted_old_password),),
                              ('new_psw', pytis.data.sval(encrypted_new_password),),))
        if not function.call(row)[0][0].value():
            pytis.form.run_dialog(pytis.form.Error, _(u"Heslo se změnit nepodařilo"))
            return
        pytis.form.run_dialog(pytis.form.Message, _(u"Heslo bylo změněno"))

    def on_new_record(self, *args, **kwargs):
        return None

    def on_edit_record(self, row):
        return None

    def on_delete_record(self, row):
        return None

class Users(Specification):
    public = True
    table = db_pytis_crypto.EPytisCryptoKeys
    title = _(u"Uživatelé")

    def _customize_fields(self, fields):
        fields.append(Field('admin_address', _(u"E-mailová adresa administrátora"),
                            virtual=True, type=pytis.data.String(not_null=True)))
        fields.append(Field('admin_password', _(u"Heslo administrátora"),
                            virtual=True, type=pytis.data.Password(not_null=True, verify=False)))
    columns = ('username', 'fresh',)
    layout = ('name', 'username', 'admin_address', 'admin_password',)

    class _InsertForm(pytis.form.PopupInsertForm):
        def _exit_check(self):
            return True
        def _commit_form(self, close=True):
            import config
            connection_data = config.dbconnection
            row = self._row
            error = pytis.extensions.add_crypto_user(row['name'].value(),
                                                     row['username'].value(),
                                                     'admin',
                                                     row['admin_password'].value(),
                                                     row['admin_address'].value(),
                                                     connection_data, transaction=self._transaction)
            if error:
                pytis.form.run_dialog(pytis.form.Error, "Error: %s" % (error,))
                return None
            if self._governing_transaction is None and self._transaction is not None:
                self._transaction.commit()
                self.close()
            return self._row

    def on_new_record(self, prefill=None, transaction=None):
        area = pytis.form.current_form()._main_form.current_row()['name']
        if prefill is None:
            prefill = {}
        else:
            prefill = copy.copy(prefill)
        prefill['name'] = area
        spec = self._action_spec_name()
        return pytis.form.run_form(self._InsertForm, spec,
                                   prefill=prefill, transaction=transaction)

    def on_edit_record(self, row):
        pytis.form.run_dialog(pytis.form.Warning, _(u"Uživatele lze jen přidávat a odebírat"))
        return None

    def on_delete_record(self, row):
        if row['username'].value() == 'admin':
            pytis.form.run_dialog(pytis.form.Error, _(u"Administrátory mazat nelze"))
            return None
        return True
