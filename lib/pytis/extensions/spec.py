# -*- coding: iso-8859-2 -*-
#
# Copyright (C) 2005, 2006 Brailcom, o.p.s.
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

"""Funkce a t��dy pro zjednodu�en� a zp�ehledn�n� tvorby specifika�n�ch soubor�.

Do tohoto modulu pat�� v�e, co n�jak�m zp�sobem obaluje API Pytisu.  Jedn� se
v�t�inou o funkce, kter� se hod� v r�zn�ch konkr�tn�ch situac�ch, kde vyj�d�en�
n�jak� konstrukce vy�aduje slo�it�j�� z�pis, ale proto�e se tato konstrukce
�asto opakuje, je mo�n� ji parametrizovan� vytvo�it automaticky.

""" 

from pytis.extensions import *
from pytis.presentation import *

import config

# Zkratky na �asto pou��van� identifik�tory.
    
Field = FieldSpec

ASC = pytis.data.ASCENDENT
DESC = pytis.data.DESCENDANT

UPCASE = PostProcess.UPPER
LOWER = PostProcess.LOWER

ALPHA = TextFilter.ALPHA
NUMERIC = TextFilter.NUMERIC
ALPHANUMERIC = TextFilter.ALPHANUMERIC
ASCII = TextFilter.ASCII
FLOAT = TextFilter.FLOAT

ALWAYS = Editable.ALWAYS
ONCE = Editable.ONCE
NEVER = Editable.NEVER

BROWSE_FORM = FormType.BROWSE
EDIT_FORM = FormType.EDIT
INSERT_FORM = FormType.INSERT
VIEW_FORM = FormType.VIEW

# Funkce pro zjednodu�en� vytv��en� polo�ek menu.

def run_form_mitem(title, name, form_class, hotkey=None, **kwargs):
    cmd = pytis.form.Application.COMMAND_RUN_FORM
    args = dict(form_class=form_class, name=name, **kwargs)
    descr = {
        pytis.form.BrowseForm:          "��dkov� formul��",
        pytis.form.PopupEditForm:       "edita�n� formul��",
        pytis.form.Form:                "du�ln� ��dkov� formul��",
        pytis.form.CodebookForm:        "��seln�kov� formul��",
        pytis.form.DescriptiveDualForm: "du�ln� n�hledov� formul��",
        }.get(form_class, "formul��")
    help = _('Otev��t %s "%s"') % (descr, title.replace('&', ''))
    return pytis.form.MItem(title, command=cmd, args=args, hotkey=hotkey,
                            help=help)

def new_record_mitem(title, name, hotkey=None):
    cmd = pytis.form.Application.COMMAND_NEW_RECORD
    args = dict(name=name)
    help = _('Otev��t vstupn� formul�� "%s"') % title
    return pytis.form.MItem(title, command=cmd, args=args, hotkey=hotkey,
                            help=help)

def run_procedure_mitem(title, name, proc_name, hotkey=None):
    cmd = pytis.form.Application.COMMAND_RUN_PROCEDURE
    return pytis.form.MItem(title, command=cmd, hotkey=hotkey,
                            args=dict(spec_name=name, proc_name=proc_name),
                            help='Spustit proceduru "%s"' % title)

nr = new_record_mitem
rp = run_procedure_mitem
def bf(title, name, hotkey=None):
    return run_form_mitem(title, name, pytis.form.BrowseForm, hotkey)
def df(title, name, hotkey=None):
    return run_form_mitem(title, name, pytis.form.BrowseDualForm, hotkey)
def ddf(title, name, hotkey=None):
    return run_form_mitem(title, name, pytis.form.DescriptiveDualForm, hotkey)
def ef(title, name, hotkey=None):
    return run_form_mitem(title, name, pytis.form.PopupEditForm, hotkey)


# Dal�� funkce pro zjednodu�en� �asto pou��van�ch konstrukc�

def rp_handler(spec_name, proc_name, *args, **kwargs):
    """Vra� handler u�ivatelsk� akce, kter� spust� proceduru s dan�mi argumenty.

    Vr�cen� handler vyvol� proceduru 'proc_name' ze specifikace 'spec_name' a
    p�ed� j� v�echny hodnoty aktu�ln�ho ��dku odpov�daj�c� kl���m p�edan�m v
    'args'.  Args je tedy seznamem identifik�tor� sloupc�.  Hodnoty jsou
    procedu�e p�ed�ny jako pozi�n� argumenty v dan�m po�ad�.

    Kl��ov� argumenty jsou p�ed�ny beze zm�n.
    
    """
    if __debug__:
        for arg in (spec_name, proc_name) + args:
            assert isinstance(arg, types.StringType)
    return lambda row: pytis.form.run_procedure(spec_name, proc_name,
                                                *[row[key] for key in args],
                                                **kwargs)
   

def cb2colvalue(value, column=None):
    """P�eve� hodnotu pol��ka na hodnotu uveden�ho sloupce nav�zan�ho ��seln�ku.
    
    Argumenty:

      value -- Instance `Value', jej�� typ m� definov�n enumer�tor typu
        'pytis.data.DataEnumerator'.
      column -- n�zev jin�ho sloupce ��seln�ku; �et�zec.  Viz
        'pytis.data.DataEnumerator.get()'

    Pokud odpov�daj�c� ��dek nen� nalezen, bude vr�cena instance 'Value'
    stejn�ho typu, jako je typ argumentu 'value' s hodnotou nastavenou na
    'None'.  Takov�to hodnota nemus� b�t validn� hodnotou typu, ale
    zjednodu�uje se t�m pr�ce s v�sledkem.  Pokud je zapot�eb� korektn�j��ho
    chov�n�, je doporu�eno pou��t p��mo metodu 'DataEnumerator.get()'
    (nap��klad vol�n�m 'value.type().enumerator().get(value.value(), column))'.
        
    """
    assert isinstance(value, pytis.data.Value)
    assert value.type().enumerator() is not None
    if column is None:
        return value
    else:
        v = value.type().enumerator().get(value.value(), column=column)
        if v is None:
            return pytis.data.Value(value.type(), None)
        else:
            return v

        
def cb2strvalue(value, column=None):
    """P�eve� instanci 'Value' typu 'Codebook' na 'Value' typu 'String'.

    Argumenty:

      value -- Instance `pytis.data.Value' typu `pytis.data.Codebook'.
      column -- n�zev jin�ho sloupce ��seln�ku; �et�zec.  Viz
        `Codebook.data_value()'.

    """
    assert isinstance(value, pytis.data.Value)
    assert value.type().enumerator() is not None
    if column is None:
        v = value.value()
    else:
        col_value = cb2colvalue(value, column=column)
        if col_value:
            v = col_value.value()
        else:
            v = None
    return pytis.data.Value(pytis.data.String(), v)


def run_cb(spec, begin_search=None, condition=None, sort=(),
           columns=None, select_row=0, multirow=False):
    """Vyvol� ��seln�k ur�en� specifikac�.

    Argumenty:

      spec -- n�zev specifikace ��seln�ku.
      begin_search -- None nebo jm�no sloupce, nad kter�m se m� vyvolat
        inkrement�ln� vyhled�v�n�.
      condition -- podm�nka pro filtrov�n� z�znam�.
      sort -- �azen� (viz pytis.data.select())
      columns -- seznam sloupc�, pokud se m� li�it od seznamu uveden�ho
        ve specifikaci.
      select_row -- ��dek, na kter� se m� nastavit kurzor.
      multirow -- umo�n� v�b�r v�ce ��dk�.
    
    Vrac� None (pokud nen� vybr�n ��dn� ��dek) nebo vybran� ��dek nebo
    tuple vybran�ch ��dk� (pokud je argument multirow nastaven).
    
    """
    if multirow:
        class_ = pytis.form.SelectRowsForm
    else:    
        class_ = pytis.form.CodebookForm
    return pytis.form.run_form(class_, spec, columns=columns,
                               begin_search=begin_search,
                               condition=condition,
                               select_row=select_row)


def help_window(inputfile=None, format=TextFormat.PLAIN):
    if not inputfile:
        pytis.form.run_dialog(pytis.form.Warning, _("Textov� soubor nenalezen"))
        return
    path = os.path.join(config.help_dir, inputfile)
    if not os.path.exists(path):
        dir, xx = os.path.split(os.path.realpath(pytis.extensions.__file__))
        p = os.path.normpath(os.path.join(dir, '../../../doc', inputfile))
        if os.path.exists(p):
            path = p
        else:
            log(OPERATIONAL, "Soubor nenalezen:", p)
    try:
        f = open(path, 'r')
    except IOError, e:
        pytis.form.run_dialog(pytis.form.Error,
                              _("Nemohu otev��t soubor n�pov�dy: %s") % e)
    else:
        text = f.read()
        f.close()
        pytis.form.InfoWindow("N�pov�da", text=text, format=format)
        

if hasattr(pytis, 'form'):
    def run_any_form():
        result = pytis.form.run_dialog(pytis.form.RunFormDialog)
        if result is not None:
            pytis.form.run_form(*result)
    cmd_run_any_form = \
        pytis.form.Application.COMMAND_HANDLED_ACTION(handler=run_any_form)


def printdirect(resolver, spec, print_spec, row):
    """Tiskni specifikaci pomoc� p��kazu config.printing_command."""
    import pytis.output
    class _PrintResolver (pytis.output.OutputResolver):
        P_NAME = 'P_NAME'
        class _Spec:
            def body(self, resolver):
                return None
            def doc_header(self, resolver):
                return None
            def doc_footer(self, resolver):
                return None
            def coding(self, resolver):
                if wx.Font_GetDefaultEncoding() == \
                   wx.FONTENCODING_ISO8859_2:
                    result = pytis.output.Coding.LATIN2
                else:
                    result = pytis.output.Coding.ASCII
                return result
        def _get_module(self, module_name):
            try:
                result = pytis.output.OutputResolver._get_module(self,
                                                               module_name)
            except ResolverModuleError:
                result = self._Spec()
            return result
        
    log(EVENT, 'Vyvol�n� tiskov�ho formul��e')
    spec_path = os.path.join('output', print_spec)
    P = _PrintResolver    
    parameters = {(spec+'/'+pytis.output.P_ROW): row}
    parameters.update({P.P_NAME: spec})
    print_resolver = P(resolver, parameters=parameters)
    resolvers = (print_resolver,)
    formatter = pytis.output.Formatter(resolvers, spec_path)
    formatter.printdirect()



class ReusableSpec:
    def __init__(self, resolver):
        self._resolver = resolver
        self._bindings = self._bindings()
        self._fields = self._fields()

    def __getitem__(self, id):
        return find(id, self._fields, key=lambda f: f.id())

    def _bindings(self):
        pass

    def _fields(self):
        pass

    def fields(self, *args):
        """Vra� seznam specifikac� sloupc� vyjmenovan�ch sloupc�.

        Pokud nejsou vyjmenov�ny ��dn� identifik�tory sloupc�, vr�t� seznam
        v�ech sloupc�.  Vrac� sekvenci instanc� 'FieldSpec'.

        """
        if len(args) == 0:
            return self._fields
        else:
            return filter(lambda f: f.id() in args, self._fields)

    def bindings(self, *args):
        """Vra� seznam specifikac� sloupc� vyjmenovan�ch sloupc�.

        Pokud nejsou vyjmenov�ny ��dn� identifik�tory sloupc�, vr�t� seznam
        v�ech sloupc�.  Vrac� sekvenci instanc� 'pytis.data.DBColumnBinding'.

        """
        if len(args) == 0:
            return self._bindings
        else:
            return filter(lambda b: b.id() in args, self._bindings)


    def fields_complement(self, *args):
        """Vra� seznam specifikac� sloupc�, kter� nejsou vyjmenov�ny.

        Pokud nejsou vyjmenov�ny ��dn� identifik�tory sloupc�, vr�t� seznam
        v�ech sloupc�.  Vrac� sekvenci instanc� 'FieldSpec'.

        """
        if len(args) == 0:
            return self._fields
        else:
            return filter(lambda f: f.id() not in args, self._fields)


