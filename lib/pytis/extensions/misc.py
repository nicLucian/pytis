# -*- coding: iso-8859-2 -*-

# Copyright (C) 2002, 2003, 2005 Brailcom, o.p.s.
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

"""Definice �asto pou��van�ch funkc� a utilit pro Pytis aplikace.""" 

from pytis.extensions import *

import pytis.output
import pytis.form
import pytis.data
import re
# TODO: je to tu pot�eba?  P��le�itostn� smazat!
from pytis.presentation import *
from pytis.util import *
from pytis.form import *

import config


def cfg_param(column, cfgspec='Nastaveni', value_column=None):
    """Vrac� instanci Value pro konfigura�n� parametr.

    Argumenty:

      column -- n�zev sloupce v konfigura�n� tabulce uveden� ve specifikaci
        udan� druh�m parametrem.
      cfgspec -- voliteln� n�zev specifikace s vazbou na konfigura�n� tabulku.
      value_column -- pokud je po�adavan� sloupec Codebook, umo��uje z�skat
        hodnotu u�ivatelsk�ho sloupce.

    """
    global cfg_objects
    data_object = None
    try:
        data_object = cfg_objects[cfgspec]
    except NameError:
        cfg_objects = {}
    except KeyError:
        pass
    if not data_object:    
        resolver = pytis.form.resolver()
        cfg = resolver.get(cfgspec, 'data_spec')
        data_object = cfg.create(dbconnection_spec=config.dbconnection)
        cfg_objects[cfgspec] = data_object
    data_object.select()
    cfg_row = data_object.fetchone()
    if not cfg_row.has_key(column):
        return pytis.data.Value(None, None)
    value = cfg_row[column]
    if isinstance(value.type(), pytis.data.Codebook):
        return cb2colvalue(value, column=value_column)
    else:
        return value


def cb_computer(codebook, column, default=None):
    """Vra� 'Computer' dopo��t�vaj�c� hodnotu ze sloupce ��seln�ku.

    Vytvo� instanci 'Computer', jej�� dopo��t�vac� funkce vrac� hodnotu sloupce
    ��seln�ku.  Computer automaticky z�vis� na dan�m ��seln�kov�m pol��ku.

    Argumenty:
      'codebook' -- id ��seln�kov�ho pol��ka, z jeho� datov�ho objektu m� b�t
        hodnota vyzvednuta.
      'column' -- id sloupce v datov�m objektu ��seln�ku, jeho� hodnota m� b�t
        dopo��t�vac� funkc� vr�cena.
      'default' -- implicitn� hodnota, kter� bude dopo��t�vac� funkc�
        vr�cena, pokud nen� hodnota ��seln�kov�ho pol��ka definov�na (je None).
    
    """
    assert isinstance(codebook, types.StringType)
    assert isinstance(column, types.StringType)
    def func(row):
        cbvalue = row[codebook]
        if cbvalue.value() is None:
            value = default
        else:
            value = cb2colvalue(cbvalue, column=column).value()
        return value
    return Computer(func, depends=(codebook,))


def cb2colvalue(value, column=None):
    """P�eve� instanci 'Value' typu 'Codebook' na 'Value' uveden�ho sloupce.
    
    Pokud sloupec nen� uveden, vr�t� instanci 'Value' sloupce odpov�daj�c�ho
    kl��ov�mu sloupci.

    Argumenty:

      value -- Instance `Value' typu `pytis.data.Codebook'.
      column -- n�zev jin�ho sloupce ��seln�ku; �et�zec. Viz
        'pytis.data.Codebook.data_value()'
        
    """
    assert isinstance(value, pytis.data.Value)
    assert isinstance(value.type(), pytis.data.Codebook)
    v, e = value.type().validate(value.export())
    if not v:
        #TODO: Co to je?
        return pytis.data.Value(None, None)
    elif column is None:
        return v
    else:
        return v.type().data_value(v.value(), column=column)

    
def cb2strvalue(value, column=None):
    """P�eve� instanci 'Value' typu 'Codebook' na 'Value' typu 'String'.

    Argumenty:

      value -- Instance `pytis.data.Value' typu `pytis.data.Codebook'.
      column -- n�zev jin�ho sloupce ��seln�ku; �et�zec.  Viz
        `Codebook.data_value()'.

    """
    assert isinstance(value, pytis.data.Value)
    assert isinstance(value.type(), pytis.data.Codebook) 
    if column is None:
        v = value.value()
    else:
        col_value = cb2colvalue(value, column=column)
        if col_value:
            v = col_value.value()
        else:
            v = None
    return pytis.data.Value(pytis.data.String(), v)


def dbfunction(name, *args, **kwargs):
    """Zavolej datab�zovou funkci a vra� v�sledek jako Pythonovou hodnotu.

    Argumenty:

      name -- n�zev funkce.
      args -- argumenty vol�n� funkce; sekvence dvouprvkov�ch tupl�, kde prvn�
        prvek je n�zev argumentu a druh� jeho hodnota jako instance 'Value'.
      proceed_with_empty_values -- pokud je pravdiv�, vol� datab�zovou funkci
        v�dy.  V opa�n�m p��pad� (v�vchoz� chov�n�) testuje, zda v�echny
        argumenty obsahuj� nepr�zdnou hodnotu (jejich vnit�� hodnota nen� None
        ani pr�zdn� �et�zec) a pokud test neprojde, vr�t� None bez vol�n�
        datab�zov� funkce.  To znamen� �sporu pokud je tato funkce pou�ita v
        computeru pol��ka, kter� je z�visl� na jin�ch pol��k�ch, kter� je�t�
        nejsou vypln�na.

    """
    def proceed_with_empty_values(proceed_with_empty_values=False):
        return proceed_with_empty_values
    if not proceed_with_empty_values(**kwargs):
        for id, v in args:
            value = v.value()
            if value is None or value == '':
                return None
    op = lambda: pytis.data.DBFunctionDefault(name, config.dbconnection)
    success, function = pytis.form.db_operation(op)
    op = lambda: function.call(pytis.data.Row(args))[0][0]
    success, result = pytis.form.db_operation(op)
    return result.value()


def dbselect(data_spec, *args, **kwargs):
    """Zavolej nad tabulkou dan� specifikace select s dan�mi argumenty.

    Argumenty:

      data_spec -- specifikace datov�ho objektu nad kter�m m� b�t proveden
        select; instance t��dy 'pytis.data.DBDataDefault'
      args, kwargs -- argumenty vol�n� 'pytis.data.select()'.
        
    Vrac� v�echny ��dky vr�cen� z datab�ze jako list.
    
    """
    op = lambda: data_spec.create(dbconnection_spec=config.dbconnection)
    success, data = pytis.form.db_operation(op)
    condition=None
    sort=()
    if kwargs.has_key('condition'):
        condition=kwargs['condition']
    if kwargs.has_key('sort'):
        condition=kwargs['sort']
    data.select(condition=condition, sort=sort)
    result = []
    while True:
        row = data.fetchone()
        if row is None:
            data.close()
            break
        result.append(row)
    return result

def dbupdate_many(spec, condition=None, update_row=None):
    """Provede update nad tabulkou danou specifikac�.

    Argumenty:

      spec -- specifikace datov�ho objektu nad kter�m m� b�t proveden
        select; string'
      condition -- podm�nka updatovan�.
      update_row -- ��dek kter�m se provede update, 
        
    Vrac� po�et updatovan�ch ��dk�.
    
    """
    resolver = pytis.form.resolver()    
    if condition is None or not isinstance(condition,pytis.data.Operator):
        raise "Nebyla p�ed�na pro update_many"
    elif update_row is None or not isinstance(update_row,pytis.data.Row):
        raise "Nebyl p�ed�n ��dek pro update"
    data_spec = resolver.get(spec, 'data_spec')
    if not data_spec:
        raise "Specifikace %s nebyla nalezena!" % (spec)
    op = lambda: data_spec.create(dbconnection_spec=config.dbconnection)
    success, data = pytis.form.db_operation(op)
    if not success:
        raise "Nepoda�ilo se vytvo�it datov� objekt pro %s!" % (spec)
    result = data.update_many(condition, update_row) 
    return result


def session_date(*args):
    """Vra� vnit�n� hodnotu nastaven�ho pracovn�ho datumu."""
    return session_date_value().value()

def session_date_value():
    """Vra� nastaven� pracovn� datum p�ihl�en�ho u�ivatele."""
    return cfg_param('datum', 'NastaveniUser')

def start_date(*args):
    """Vra� vnit�n� hodnotu nastaven�ho 'datumu od'."""
    return start_date_value().value()

def start_date_value():
    """Vra� nastaven� 'datum od' p�ihl�en�ho u�ivatele."""
    return cfg_param('datum_od', 'NastaveniUser')

def end_date(*args):
    """Vra� vnit�n� hodnotu nastaven�ho 'datumu do'."""
    return end_date_value().value()

def end_date_value():
    """Vra� nastaven� 'datum do' p�ihl�en�ho u�ivatele."""
    return cfg_param('datum_do', 'NastaveniUser')

def printdirect(resolver, spec, print_spec, row):
    """Tiskni specifikaci pomoc� p��kazu config.printing_command."""
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


def smssend(tel, message):
    import os, os.path, commands

    SERVER='192.168.1.55'
    UID='sms'
    PWD='sms'
    DB='SMS'
    MAX_LENGTH=480 # 3 SMS po 160 znac�ch
    SQSH='/usr/bin/sqsh'
    TEMPLATE="""
    insert into sms_request
    (tel_num_to, message_typ, request_typ, id_module, user_data)
    values
    ('%s', 0, 0, 0, '%s')
    """


    if not os.path.exists(SQSH):
        return "Nen� nainstalov�n bal�k 'sqsh'. SMS nebude odesl�na."
    if len(message) > MAX_LENGTH:
        return "Zpr�va je del�� ne� %s. SMS nebude odesl�na." % (MAX_LENGTH)
    if len(tel) == 13 and tel[0:4] == '+420':
	tel = '00420' + tel[4:]
    elif (len(tel) == 14 and tel[0:5] <> '00420') or len(tel) <> 9:
	return ("�patn� from�t telefon�ho ��sla %s." + \
	        "��slo mus� m�t tvar:\n00420xxxxxxxxx\n+420xxxxxxxxx\n" + \
		"xxxxxxxxx") % (tel) 
    message.replace('"','')
    message.replace("'","")	
    sms_insert = TEMPLATE % (tel, message)
    cmd = '%s -U %s -D %s -S %s -P %s -C "%s"' % \
	  (SQSH, UID, DB, SERVER, PWD, sms_insert)
    test, msg = commands.getstatusoutput(cmd)
    if test:
	msg = "SMS se nepoda�ilo odeslat!\n\n" + msg
	return msg
    return None
        
def run_cb(spec, begin_search=None, condition=None, columns=None,
           returned_column=None, select_row=0):
    """Vyvol� ��seln�k ur�en� specifikac�.

    Argumenty:

      spec -- n�zev specifikace obsahuj�c� metodu 'cb_spec'
      begin_search -- None nebo jm�no sloupce, nad kter�m se m� vyvolat
        inkrement�ln� vyhled�v�n�.
      condition -- podm�nka pro filtrov�n� z�znam�
      columns -- seznam sloupc�, pokud se m� li�it od seznamu uveden�mu
        ve specifikaci
      returned_column -- n�zev sloupce, jeho� hodnota se m� vr�tit, pokud
        se li�� od n�zvu uveden�ho ve specifikaci
      select_row -- ��dek, na kter� se m� nastavit kurzor
        
    Vrac� None (pokud nen� vybr�n ��dn� ��dek) nebo instanci 'Value'
    pro sloupec 'returned_column'.
    """
    resolver = pytis.form.resolver()
    cbspec = resolver.get(spec, 'cb_spec')
    if not columns:
        columns = cbspec.columns()
    if not returned_column:    
        returned_column = cbspec.returned_column()
    result = run_form(CodeBook, cbspec.name(), columns=columns,
                     begin_search=begin_search,
                     condition=condition, 
                     select_row=select_row)
    if result:
        return result[returned_column]

def row_update(row, values=()):
    """Provede update nad p�edan�m ��dkem.

    Argumenty:

      row -- p�edan� instance aktu�ln�ho PresentedRow.
      values -- sekvence dvouprvkov�ch sekvenc� ('id', value) ,
        kde 'id' je �et�zcov� identifik�tor pol��ka a value je
        instance, kterou se bude pol��ko aktualizovat.
    """        
    data = row.data()
    updaterow = row.row()
    key = data.key()
    if is_sequence(key):
        key = key[0]
    for col, val in values:
        updaterow[col] = val
    data.update(row[key.id()], updaterow)

def flatten_menus():
    """Vytvo�� jedno�rov�ov� seznam polo�ek menu.

       Vrac� seznam odpov�daj�c�ch slovn�kov�ch hodnot, pro ka�dou polo�ku
       menu. Slou�� jako pomocn� funkce pro snadn�j�� zpracov�n� polo�ek
       v menu, nap�. p�i sestavov�n� p�ehledu n�zv� pou�it�ch polo�ek a jejich
       specifikac�.
    """    
    TYPES = ('M', 'F', 'S', 'I')
    RF = pytis.form.Application.COMMAND_RUN_FORM
    resolver = pytis.form.resolver()
    def flatten(flatten, queue, found, level=0):
        if queue:
            iappend = ()
            head = queue[0]
            tail = queue[1:]
            if isinstance(head, pytis.form.Menu):
                found.append({'type': 'M',
                              'title': head.title(),
                              'level': level})
                result = flatten(flatten, head.items(),
                                 found, level=level+1)
            elif isinstance(head, pytis.form.MSeparator):
                found.append({'type': 'S',
                              'level': level})
            elif isinstance(head, pytis.form.MItem):
                title = head.title()
                if head.command() == RF:
                    spec = head.args()['name']
                    form = str(head.args()['form_class'])
                    form = form.split('.')[-1][:-2]
                    found.append({'type': 'F',
                                  'form': form,
                                  'spec': spec,
                                  'title': title,
                                  'level': level})
                else:
                    found.append({'type': 'I',
                                  'title': title,
                                  'level': level})
            result = flatten(flatten, tail, found, level=level)
        else:
            result = found                
        return result
    menus = resolver.get('application', 'menu')
    menus = flatten(flatten, menus, [])
    return menus

def menu_report():
    """Vytv��� p�ehledn� n�hled na polo�ky menu."""
    DUALS = ('BrowseDualForm',)
    MAX_WIDTH = 150
    PRAVA = (pytis.data.Permission.VIEW,
             pytis.data.Permission.INSERT,
             pytis.data.Permission.UPDATE,
             pytis.data.Permission.DELETE,
             pytis.data.Permission.EXPORT
             )
    resolver = pytis.form.resolver()
    menus = flatten_menus()
    radky = []
    data_specs = []
    for m in menus:
        if m['type'] in ('M', 'I'):
            radek = "  "*m['level'] + m['title']        
        elif m['type'] == 'F':
            radek = "  "*m['level'] + m['title']
            radek = radek + "  <%s:%s>" % (m['spec'], m['form'])
            spec = m['spec']
            if m['form'] in DUALS:
                dual_spec = resolver.get(spec, 'dual_spec')
                main = dual_spec.main_name()
                side = dual_spec.side_name()
                radek = radek + "  (Main: %s, Side: %s)" % (main, side)
                data_specs.append(main)
                data_specs.append(side)
            else:
                data_specs.append(spec)                
        elif m['type'] == 'S':
            radek = "  "*m['level'] + '__________'
        radky.append(radek)
    data_specs = remove_duplicates(data_specs)
    data_specs.sort()
    radky.append("\n\nP�ehled pr�v pro jednotliv� specifikace:")    
    radky.append("========================================\n")    
    for s in data_specs:
        radky.append(s)
        try:
            data = resolver.get(s, 'data_spec')
            prava = data.access_rights()            
            if prava:
                for p in PRAVA:
                    egroups = prava.permitted_groups(p, None)
                    if egroups:
                        radky.append("  %s pr�va: " % (p) + ', '.join(egroups))
        except Exception, e:
            radky.append("  Export pr�va: CHYBA! Specifikace nenalezena.")            
    obsah = "\n".join(radky)    
    width = min(max([len(x) for x in radky]), MAX_WIDTH)
    pytis.form.run_dialog(pytis.form.InputDialog,
                          message="P�ehled menu polo�ek a n�zv� specifikac�",
                          value=obsah,
                          input_width=width,
                          input_height=50)

def check_form():
    """Zept� se na n�zev specifikace a zobraz� jej� report."""
    resolver = pytis.form.resolver()
    spec = pytis.form.run_dialog(pytis.form.InputDialog,
                               message="Kontrola defsu",
                               prompt="Specifikace",
                               input_width=30)
    if spec:
        try:
            data_spec = resolver.get(spec, 'data_spec')
            view_spec = resolver.get(spec, 'view_spec')                
        except ResolverError:
            msg = 'Specifikace nenalezena.'
            pytis.form.run_dialog(pytis.form.Warning, msg)
            return
        data = data_spec.create(dbconnection_spec=config.dbconnection)
        # Pol��ka v bindings
        cols = [c.id() for c in data.columns() if c.id()!='oid']
        obsah = "Pol��ka v data_spec:\n"
        obsah = obsah + "\n".join(cols)
        # N�zev tabulky
        table = data.table(cols[0])
        obsah = obsah + "\n\nTabulka: %s" % (table)
        # Pol��ka v bindings
        fields = [f.id() for f in view_spec.fields()]
        obsah = obsah + "\n\nPol��ka ve fields:\n"
        obsah = obsah + "\n".join(fields)
        # Title
        title = view_spec.title()
        obsah = obsah + "\n\n"
        obsah = obsah + "Title: %s" % (title)
        # Popup menu
        popup_menu = view_spec.popup_menu()
        if popup_menu:                
            popup_items = [p.title() for p in popup_menu]
            obsah = obsah + "\n\nPolo�ky popup_menu:\n"
            obsah = obsah + "\n".join(popup_items)
        pytis.form.run_dialog(pytis.form.InputDialog,
                            message="DEFS: %s" % (spec),
                            value=obsah,
                            input_width=100,
                            input_height=50)

def check_defs(seznam):
    """Zkontroluje datov� specifikace pro uveden� seznam.

    Argumenty:
      seznam -- seznam n�zv� specifikac�

    """
    resolver = pytis.form.resolver()
    errors = []
    dbconn = dbconnection_spec=config.dbconnection
    def check_spec(update, seznam):
        total = len(seznam)
        last_status = 0
        step = 5 # aktualizujeme jen po ka�d�ch 'step' procentech...
        for n, s in enumerate(seznam):
            status = int(float(n)/total*100/step)
            if status != last_status:
                last_status = status 
                if not update(status*step):
                    break
            try:
                data_spec = resolver.get(s, 'data_spec')
                view_spec = resolver.get(s, 'view_spec')
                try:
                    data = data_spec.create(dbconnection_spec=dbconn)
                except Exception, e:
                    err = """Specifikace %s: %s""" % (s, str(e))
                    errors.append(err)
            except ResolverError, e:
                err = """Specifikace %s: %s""" % (s, str(e))
    msg = 'Kontroluji datov� specifikace...'
    pytis.form.run_dialog(pytis.form.ProgressDialog, check_spec, args=(seznam,),
                        message=msg, elapsed_time=True, can_abort=False)
    if errors:
        obsah = "\n".join(errors)
        pytis.form.run_dialog(pytis.form.InputDialog,
                            message="Chyby ve specifikac�ch",
                            value=obsah,
                            input_width=100,
                            input_height=50)

def check_all_defs():
    import re
    files = [os.path.splitext(x)[0] for x in os.listdir(config.def_dir)
             if not re.search('[#~_]', x) and x.endswith('.py')]
    return check_defs(files)
 
def check_menus_defs():        
    menus = flatten_menus()
    seznam = [m['spec'] for m in menus
              if m.has_key('form')]
    return check_defs(seznam)
            
def constraints_email(email):
    """Kontroluje string podle re v�razu. Pokud odpov�d� nebo je None funkce
    vrac� None. Jinak vrac� string s chybovou hl�kou"""
    if email is None:
        return None
    mask=re.compile(r"^[A-Za-z\d]([\w\d\.-]?[A-Za-z\d])*\@[A-Za-z\d]([\w\d\.-]?[A-Za-z\d])*$")
    if mask.match(email.strip()) is None:
        return "�patn� tvar emailu " + email.strip()  + " !"
    return None

def constraints_email_many(emails):
    """Kontroluje string podle re v�razu. Pokud odpov�d� nebo je None funkce
    vrac� None. Jinak vrac� string s chybovou hl�kou"""
    if emails is None:
        return None
    not_match=[]
    for email in emails.split(','):
        result = constraints_email(email)
        if not result is None:
            not_match.append(result)
    if len(not_match) == 0:
        return None
    return '\n'.join(not_match)


