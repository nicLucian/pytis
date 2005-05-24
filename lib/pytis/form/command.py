# -*- coding: iso-8859-2 -*-

# Definice u�ivatelsk�ch p��kaz�
# 
# Copyright (C) 2002, 2003, 2004, 2005 Brailcom, o.p.s.
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

"""Definice u�ivatelsk�ch p��kaz�.

Tento soubor obsahuje jednak t��du 'Command', slou��c� k�definici v�ech
podporovan�ch p��kaz�, a�jednak definice p��kaz�.

V�echny p��kazy jsou centr�ln� definov�ny zde, z�d�vodu konzistence a
p�ehlednosti, zejm�na z�pohledu tv�rc� definic aplikac�.  V�echny definovan�
p��kazy jsou konstantami n�kter� z�t��d modulu 'pytis.form'; n�zvy t�chto
konstant za��naj� prefixem 'COMMAND_' (tuto konvenci je nutno dodr�ovat).

P�i�azen� kl�ves p��kaz�m:

V�aplikaci mimo modul 'defs' nepou��v�me p��m� z�pis kl�ves, n�br� pouze jim
odpov�daj�c� p��kazy.  To n�m umo��uje nestarat se v�aplika�n�m k�du
o�p�i�azen� kl�ves, ta definujeme na jedin�m m�st� v�tomto modulu.

"""


from pytis.form import *


class Command:
    """Reprezentace p��kazu u�ivatelsk�ho rozhran�.

    Kl�vesa, kter� p��kaz vyvol�v�, je dostupn� ve form� ve�ejn�ho atributu
    `key' a jej� hodnotu lze v�defini�n�ch souborech konkr�tn� aplikace
    prost�ednictv�m tohoto atributu zm�nit.

    P�i definici u�ivatelsk�ch p��kaz� lze definovat vlastn� obslu�n� rutiny
    pro jejich zpracov�n�.  U�ivatelsk�m p��kazem je my�len p��kaz, kter� nen�
    standardn� o�et�ov�n ��dnou t��dou u�ivatelsk�ho rozhran� (formul��em).
    Pokud v�ak formul�� podporuje u�ivatelsk� p��kazy, vyvol� funkci
    specifikovanou argumentem konstruktoru 'handler' s parametry, kter� z�vis�
    na typu dan� t��dy u�ivatelsk�ho rozhran�. T��da BrowseForm tak nap��klad
    jako argument p�ed� data aktu�ln�ho ��dku seznamu apod. V�ce v dokumentaci
    jednotliv�ch formul��ov�ch t��d.
    
    Identifik�tor p��kazu je v�tuto chv�li v�znamn� pouze pro logov�n�.
    P��kazy jsou rozpozn�v�ny dle konkr�tn�ch instanc�, ne podle sv�ho
    identifik�toru.

    """
    def __init__(self, id, key=None, handler=None, log_=True,
                 access_groups=None):
        """Definuj p��kaz.

        Argumenty:

          id -- identifik�tor p��kazu, libovoln� nepr�zdn� �et�zec mezi
            identifik�tory p��kazu unik�tn�
          handler -- funkce volan� p�i zpracov�n� p��kazu.  M� v�znam p�i
            definici u�ivatelsk�ch p��kaz�.  Bl��e viz dokumentace t��dy.
            Hodnotou je callable object, nebo None.
          log_ -- pr�v� kdy� je pravdiv�, je vyvol�n� p��kazu logov�no jako
            EVENT, jinak je logov�no pouze jako DEBUG
          access_groups -- sekvence jmen skupin (strings), kter� maj� pr�vo
            p��kaz vyvolat; m��e b�t t� 'None', v�kter�m�to p��pad� p��kaz
            mohou vyvolat v�echny skupiny.  Toto opr�vn�n� je form�ln�,
            zohledn�n� jen v�u�ivatelsk�m rozhran�, nem� faktickou bezpe�nostn�
            roli.
    
        """
        assert is_anystring(id)
        assert key is None or is_string(key) or is_sequence(key)
        self._id = id
        if key is not None:
            log(OPERATIONAL,
                "Pou�it potla�en� argument `key' t��dy `Command':", (key, id))
            self.key = xtuple(key)
        self._handler = handler
        self._log = log_
        if access_groups is not None:
            access_groups = xtuple(access_groups)
        self._access_groups = access_groups
    
    def id(self):
        """Vra� identifik�tor zadan� v�konstruktoru."""
        return self._id

    def handler(self):
        """Vra� rutinu pro zpracov�n� p��kazu."""
        return self._handler

    def access_groups(self):
        """Vra� tuple jmen skupin (strings) s�pr�vem p��stupu nebo 'None'.

        Vr�cen� hodnota odpov�d� argumentu `access_groups' konstruktoru.

        """
        return self._access_groups

    def log_kind(self):
        """Vra� druh logovac� hl�ky, pod kter�m m� b�t p��kaz logov�n."""
        if self._log:
            kind = EVENT
        else:
            kind = DEBUG
        return kind

    def __cmp__(self, other):
        if sameclass(self, other):
            if self._id == other._id:
                return 0
            elif self._id < other._id:
                return -1
            else:
                return 1
        else:
            return compare_objects(self, other)
        
    def __str__(self):
        return '<Command: %s>' % (self._id,)

    def __setattr__(self, name, value):
        # TODO: �asem zru�it.
        if name == 'key':
            log(OPERATIONAL,
                "Nastaven potla�en� atribut `key' t��dy `Command':",
                (value, self._id))
        self.__dict__[name] = value
            

def invoke_command(command, **kwargs):
    """Vyvolej glob�ln� zpracov�n� p��kazu 'command'.

    Argumenty:

      command -- instance t��dy 'Command'
      kwargs -- parametry p��kazu

    """
    return pytis.form.application._application.on_command(command, **kwargs)


Application.COMMAND_EXIT = Command('application.exit')
"""Ukon�en� aplikace."""
Application.COMMAND_RUN_FORM = Command('application.run-form')
"""Spu�t�n� formul��e."""
Application.COMMAND_RUN_PROCEDURE = Command('application.run-procedure')
"""Spu�t�n� procedury."""
Application.COMMAND_NEW_RECORD = Command('application.new-record')
"""Vlo�en� nov�ho z�znamu."""
Application.COMMAND_LEAVE_FORM = Command('application.leave-form')
"""Odstran�n� aktivn�ho okna formul��e z�aplikace."""
Application.COMMAND_RAISE_FORM = Command('application.raise-form')
"""Vyzvednut� okna formul��e v okn� aplikace (argument je instance `Form')."""
Application.COMMAND_PREV_FORM = Command('application.prev-form')
"""Vyzvednut� okna formul��e p�edch�zej�c�ho aktivn� okno."""
Application.COMMAND_NEXT_FORM = Command('application.next-form')
"""Vyzvednut� okna formul��e n�sleduj�c�ho za aktivn�m oknem."""
Application.COMMAND_BREAK = Command('application.break')
"""P�eru�en� aktu�ln� prov�d�n� operace."""
Application.COMMAND_REFRESH = Command('application.refresh')
"""Vy��d�n� obnoven� obsahu aktivn�ho formul��e."""
Application.COMMAND_SHOW_POPUP_MENU = Command('application.show-popup-menu')
"""Zobraz kontextov� menu aktivn�ho prvku, pokud to pro dan� prvek lze."""

Form.COMMAND_PRINT = Command('form.print')
"""Tisk aktu�ln�ho obsahu formul��e."""

LookupForm.COMMAND_FILTER = Command('lookup-form.filter')
"""Filtrov�n� z�znam�."""
LookupForm.COMMAND_JUMP = Command('lookup-form.jump')
"""Skok na z�znam."""
LookupForm.COMMAND_SEARCH = Command('lookup-form.search')
"""Hled�n� z�znamu."""
LookupForm.COMMAND_SEARCH_PREVIOUS = Command('lookup-form.search')
"""Hled�n� P�edchoz�ho z�znamu bez dialogu."""
LookupForm.COMMAND_SEARCH_NEXT = Command('lookup-form.search')
"""Hled�n� dal��ho z�znamu bez dialogu."""
LookupForm.COMMAND_SORT_COLUMN = Command('lookup-form.sort-column')
"""Set��d�n� podle sloupce."""

ListForm.COMMAND_ACTIVATE = Command('list-form.activate')
"""Vyvol�n� aktiva�n� funkce pro ��dek ��dkov�ho formul��e."""
ListForm.COMMAND_ACTIVATE_ALTERNATE = Command('list-form.activate-alternate')
"""Vyvol�n� alternativn� aktiva�n� funkce pro ��dek ��dkov�ho formul��e."""
ListForm.COMMAND_SELECT_CELL = Command('list-form.select-cell', log_=False)
"""V�b�r bu�ky seznamu."""
ListForm.COMMAND_FIRST_COLUMN = Command('list-form.first-column', log_=False)
"""P�echod na prvn� sloupec tabulky."""
ListForm.COMMAND_LAST_COLUMN = Command('list-form.last-column', log_=False)
"""P�echod na posledn� sloupec tabulky."""
ListForm.COMMAND_INCREMENTAL_SEARCH = Command('list-form.incremental-search')
"""Prefixov� inkrement�ln� hled�n� z�znamu."""
ListForm.COMMAND_FULL_INCREMENTAL_SEARCH = Command('list-form.full-incremental-search')
"""Pln� inkrement�ln� hled�n� z�znamu."""
ListForm.COMMAND_EDIT = Command('list-form.edit')
"""Vyvol�n� inline editace aktu�ln� bu�ky."""
ListForm.COMMAND_COPY_CELL = Command('list-form.copy-cell')
"""Zkop�rov�n� obsahu aktu�ln� bu�ky do clipboardu."""
ListForm.COMMAND_FILTER_BY_CELL = Command('list-form.filter-by-cell')
"""Vyfiltrov�n� formul��e podle hodnoty aktu�ln� bu�ky."""
ListForm.COMMAND_EXPORT_CSV = Command('list-form.export-csv')
"""Export ��dkov�ho formul��e do csv souboru."""
ListForm.COMMAND_LINE_COMMIT = Command('list-form.line-commit')
"""Dokon�en� editace z�znamu (ulo�en�)."""
ListForm.COMMAND_LINE_ROLLBACK = Command('list-form.line-rollback')
"""Kompletn� zru�en� editace z�znamu."""
ListForm.COMMAND_LINE_SOFT_ROLLBACK = Command('list-form.line-soft-rollback')
"""Kompletn� zru�en� editace zat�m nezm�n�n�ho z�znamu."""
ListForm.COMMAND_FINISH_EDITING = Command('list-form.finish-editing')
"""Opu�t�n� editace ��dku."""
ListForm.COMMAND_LINE_DELETE = Command('list-form.line-delete')
"""Smaz�n� aktu�ln�ho z�znamu."""
ListForm.COMMAND_CELL_COMMIT = Command('list-form.cell-commit')
"""Ukon�en� editace pol��ka s�novou hodnotou."""
ListForm.COMMAND_CELL_ROLLBACK = Command('list-form.cell-rollback')
"""Ukon�en� editace pol��ka s�vr�cen�m p�vodn� hodnoty."""
ListForm.COMMAND_NEW_LINE_AFTER = Command('list-form.new-line-after')
"""Inline vlo�en� nov�ho z�znamu za aktu�ln� ��dek."""
ListForm.COMMAND_NEW_LINE_AFTER_COPY = Command('list-form.new-line-after-copy')
"""Inline vlo�en� nov�ho z�znamu za aktu�ln� ��dek jako jeho kopie."""
ListForm.COMMAND_NEW_LINE_BEFORE = Command('list-form.new-line-before')
"""Inline vlo�en� nov�ho z�znamu p�ed aktu�ln� ��dek."""
ListForm.COMMAND_NEW_LINE_BEFORE_COPY = Command('list-form.new-line-before-copy')
"""Inline vlo�en� nov�ho z�znamu p�ed aktu�ln� ��dek jako jeho kopie."""
ListForm.COMMAND_SET_GROUPING_COLUMN = Command('list-form.set-grouping-column')
"""Zm�na sloupce vizu�n�ho seskupov�n� (vy�aduje argument 'column_id')."""

BrowseForm.COMMAND_NEW_RECORD = Command('browse-form.new-record')
"""Formul��ov� editace nov�ho z�znamu v���dkov�m formul��i."""
BrowseForm.COMMAND_NEW_RECORD_COPY = Command('browse-form.new-record-copy')
"""Formul��ov� editace nov�ho z�znamu jako kopie aktu�ln�ho z�znamu."""
BrowseForm.COMMAND_RECORD_EDIT = Command('browse-form.edit-record')
"""Editace aktu�ln�ho z�znamu v popup formul��i."""

EditForm.COMMAND_RECORD_DELETE = Command('edit-form.record-delete')
"""Vymaz�n� editovan�ho z�znamu z�datab�ze."""
EditForm.COMMAND_RECORD_INSERT = Command('edit-form.record-insert')
"""Vlo�en� nov�ho z�znamu z�edita�n�ho formul��e."""
EditForm.COMMAND_RECORD_UPDATE = Command('edit-form.record-update')
"""Ulo�en� editovan�ho z�znamu v�edita�n�m formul��i."""
EditForm.COMMAND_RECORD_COMMIT = Command('edit-form.record-commit')
"""Ukon�en� edita�n�ho formul��e s ulo�en�m zm�n."""
EditForm.COMMAND_NAVIGATE = Command('edit-form.navigate')
"""Navigace mezi pol��ky edita�n�ho formul��e."""
EditForm.COMMAND_NAVIGATE_BACK = Command('edit-form.navigate-back')
"""Zp�tn� navigace mezi pol��ky edita�n�ho formul��e."""

BrowsableShowForm.COMMAND_NEXT_RECORD = Command('edit-form.next-record')
"""P�echod na dal�� z�znam."""
BrowsableShowForm.COMMAND_PREVIOUS_RECORD= Command('edit-form.previous-record')
"""P�echod na p�edchoz� z�znam."""
BrowsableShowForm.COMMAND_FIRST_RECORD = Command('edit-form.first-record')
"""P�echod na prvn� z�znam."""
BrowsableShowForm.COMMAND_LAST_RECORD = Command('edit-form.last-record')
"""P�echod na posledn� z�znam."""

DualForm.COMMAND_OTHER_FORM = Command('dual-form.other-form')
"""P�echod mezi podformul��i du�ln�ho formul��e."""

PrintForm.COMMAND_NEXT_PAGE = Command('print-form.next-page')
"""P�echod na dal�� str�nku tiskov�ho n�hledu."""
PrintForm.COMMAND_PREVIOUS_PAGE = Command('print-form.previous-page')
"""P�echod na p�edchoz� str�nku tiskov�ho n�hledu."""

InputField.COMMAND_RESET_FIELD = Command('input-field.command-reset-field')
"""Vr�cen� p�vodn� hodnoty vstupn�ho pol��ka."""
InputField.COMMAND_COMMIT_FIELD = Command('input-field.command-commit-field')
"""�sp�n� ukon�en� editace vstupn�ho pol��ka."""
InputField.COMMAND_LEAVE_FIELD = Command('input-field.command-leave-field')
"""Odchod z editace vstupn�ho pol��ka."""
Invocable.COMMAND_INVOKE_SELECTION = Command('invocable.invoke-selection')
"""Vyvol�n� v�b�ru hodnoty vstupn�ho pol��ka."""
Invocable.COMMAND_INVOKE_SELECTION_ALTERNATE = \
    Command('invocable.invoke-selection-alternate')
"""Vyvol�n� alternativn�ho zp�sobu v�b�ru hodnoty vstupn�ho pol��ka."""
ListField.COMMAND_INVOKE_EDIT_FORM = Command('list-field.invoke-edit-form')
"""Vyvol�n� edita�n�ho formul��e nad aktu�ln�m z�znamem 'ListField'."""
ListField.COMMAND_INVOKE_BROWSE_FORM = Command('list-field.invoke-browse-form')
"""Zobrazen� aktu�ln�ho z�znamu 'ListField' ve formul��i 'BrowseForm'."""
ListField.COMMAND_CHOOSE_KEY = Command('list-field.choose-key')
"""V�b�r n�vratov�ho sloupce a hodnoty pro 'ListField'."""

Dialog.COMMAND_CLOSE_DIALOG = Command('dialog.close-dialog')
"""Opu�t�n� dialogu bez potvrzen�."""
Dialog.COMMAND_COMMIT_DIALOG = Command('dialog.commit-dialog')
"""Odesl�n� dialogu stejn� jako stiskem v�choz�ho tla��tka."""

DEFAULT_COMMAND_KEYS = (
    (Application.COMMAND_BREAK,                   'Ctrl-g'),
    (Application.COMMAND_LEAVE_FORM,              'Escape'),
    (Application.COMMAND_NEXT_FORM,               'Ctrl-Down'),
    (Application.COMMAND_PREV_FORM,               'Ctrl-Up'),
    (Application.COMMAND_REFRESH,                 'Ctrl-l'),
    (Application.COMMAND_SHOW_POPUP_MENU,         'Ctrl-M'),
    (Form.COMMAND_PRINT,                         ('Ctrl-x', 'p')),
    (LookupForm.COMMAND_SORT_COLUMN,              'F4'),
    (LookupForm.COMMAND_FILTER,                   'Ctrl-F4'),
    (LookupForm.COMMAND_SEARCH_NEXT,              'Ctrl-s'),
    (LookupForm.COMMAND_SEARCH_PREVIOUS,          'Ctrl-r'),
    (LookupForm.COMMAND_SEARCH,                   'F3'),
    (LookupForm.COMMAND_JUMP,                     'Ctrl-j'),
    (ListForm.COMMAND_INCREMENTAL_SEARCH,         'Ctrl-F3'),
    (ListForm.COMMAND_FULL_INCREMENTAL_SEARCH,   ('Ctrl-u', 'Ctrl-F3')),
    (ListForm.COMMAND_ACTIVATE,                   'Enter'),
    (ListForm.COMMAND_ACTIVATE_ALTERNATE,         ' '),
    (ListForm.COMMAND_COPY_CELL,                  'Ctrl-c'),
    (ListForm.COMMAND_FIRST_COLUMN,               'Home'),
    (ListForm.COMMAND_LAST_COLUMN,                'End'),
    (ListForm.COMMAND_EXPORT_CSV,                 'Ctrl-e'),
    (ListForm.COMMAND_EDIT,                       'F9'),
    (ListForm.COMMAND_LINE_DELETE,                'F8'),
    (ListForm.COMMAND_LINE_ROLLBACK,              'Ctrl-F12'),
    (ListForm.COMMAND_FINISH_EDITING,             'Escape'),
    (ListForm.COMMAND_LINE_COMMIT,                'F12'),
    (ListForm.COMMAND_CELL_COMMIT,                'Enter'),
    (ListForm.COMMAND_CELL_ROLLBACK,              'Escape'),
    (ListForm.COMMAND_NEW_LINE_AFTER,             'Insert'),
    (ListForm.COMMAND_NEW_LINE_AFTER_COPY,        'F7'),
    (ListForm.COMMAND_NEW_LINE_BEFORE,            'Ctrl-Insert'),
    (ListForm.COMMAND_NEW_LINE_BEFORE_COPY,       'Ctrl-F7'),
    (BrowseForm.COMMAND_NEW_RECORD,               'F6'),
    (BrowseForm.COMMAND_NEW_RECORD_COPY,          'Ctrl-F6'),
    (BrowseForm.COMMAND_RECORD_EDIT,              'F5'),
    (EditForm.COMMAND_RECORD_DELETE,              'F8'),
    (EditForm.COMMAND_RECORD_INSERT,              'F7'),
    (EditForm.COMMAND_RECORD_UPDATE,              'F12'),
    (EditForm.COMMAND_RECORD_COMMIT,              'Ctrl-Enter'),
    (EditForm.COMMAND_NAVIGATE,                   'Tab'),        
    (EditForm.COMMAND_NAVIGATE_BACK,              'Shift-Tab'),        
    (BrowsableShowForm.COMMAND_NEXT_RECORD,       'Next'),
    (BrowsableShowForm.COMMAND_PREVIOUS_RECORD,   'Prior'),
    (BrowsableShowForm.COMMAND_FIRST_RECORD,      'Home'),
    (BrowsableShowForm.COMMAND_LAST_RECORD,       'End'),
    (DualForm.COMMAND_OTHER_FORM,                 'Ctrl-Tab'),
    (PrintForm.COMMAND_NEXT_PAGE,                 'Next'),
    (PrintForm.COMMAND_PREVIOUS_PAGE,             'Prior'),
    (InputField.COMMAND_COMMIT_FIELD,             'Enter'),
    (InputField.COMMAND_LEAVE_FIELD,              'Escape'),
    (Invocable.COMMAND_INVOKE_SELECTION,          'F2'),
    (Invocable.COMMAND_INVOKE_SELECTION_ALTERNATE,'Ctrl-F2'),
    (Dialog.COMMAND_CLOSE_DIALOG,                 'Escape'),
    (Dialog.COMMAND_COMMIT_DIALOG,                'Ctrl-Enter'))



if __debug__:
    Application.COMMAND_CUSTOM_DEBUG = Command('application.custom-debug')
    """Pomocn� p��kaz pro vyvol�n� pomocn� lad�c� funkce.

    Vyvolan� funkce je 'config.custom_debug'.

    """
    DEFAULT_COMMAND_KEYS += \
        ((Application.COMMAND_CUSTOM_DEBUG, 'Ctrl-Backspace'),)
