# -*- coding: iso-8859-2 -*-

# Prvky u�ivatelsk�ho rozhran� souvisej�c� s�vyhled�v�n�m
# 
# Copyright (C) 2001-2009 Brailcom, o.p.s.
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

"""Prvky u�ivatelsk�ho rozhran� souvisej�c� s�vyhled�v�n�m.

Modul obsahuje podporu dialog� s�funkcionalitou v�ce �i m�n� odpov�daj�c�
z�kladn�mu vyhled�vac�mu dialogu.  Z�kladem je spole�n� t��da 'Dialog', kter�
je m�n�na jako abstraktn�.  Z�n� jsou pak odvozeny dialogov� t��dy pro
konkr�tn� pou�it�.

"""

import pytis.data
from pytis.form import *
from pytis.presentation import *
import wx


class SFSColumn(object):
    """Column specification for dialog selectors."""

    def __init__(self, id, type, label):
        """Initialize column specification.

        Arguments:

          id -- datov� identifik�tor sloupce jako string
          type -- datov� typ sloupce jako instance t��dy
            'pytis.data.types_.Type'
          label -- jm�no sloupce pro u�ivatele jako string

        """
        self._id = id
        self._type = type
        self._label = label

    def id(self):
        """Vra� id zadan� v�konstruktoru."""
        return self._id

    def type(self):
        """Vra� type zadan� v�konstruktoru."""
        return self._type

    def label(self):
        """Vra� label zadan� v�konstruktoru."""
        return self._label

    
class SFSDialog(GenericDialog):
    """Common ancestor of all sorting/filtering/searching dialogs."""

    _FIELD_HEIGHT = 27
    _TITLE = None
    _ESCAPE_BUTTON = _("Zav��t")
    _BUTTONS = (_ESCAPE_BUTTON,)
    def __init__(self, parent, columns, col=None):
        """Initialize the dialog.

        Arguments:

          parent -- wx parent of the dialog window
          columns -- a sequence of 'SFSColumn' instances
          col -- current column identifier as a string

        """
        self._parent = parent
        self._columns = tuple(columns)
        self._col = col
        super(SFSDialog, self).__init__(parent, self._TITLE, self._BUTTONS)

    def _find_column(self, cid):
        return find(cid, self._columns, key=lambda c: c.id())
    
    def _create_button(self, label, callback, tooltip=None, **kwargs):
        return wx_button(self._dialog, label=label, callback=callback,
                         tooltip=tooltip, height=self._FIELD_HEIGHT, **kwargs)
        
    def _create_choice(self, choices, tooltip=None, **kwargs):
        return wx_choice(self._dialog, choices, height=self._FIELD_HEIGHT, **kwargs)

    def _create_text_ctrl(self, value, **kwargs):
        return wx_text_ctrl(self._dialog, value, height=self._FIELD_HEIGHT, **kwargs)

    def _create_spin_ctrl(self, value, **kwargs):
        return wx_spin_ctrl(self._dialog, value, height=self._FIELD_HEIGHT, **kwargs)
        
    def _create_label(self, label, **kwargs):
        panel = wx.Panel(self._dialog, -1)
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        label_ctrl = wx.StaticText(panel, -1, label)
        sizer.Add(label_ctrl, border=12, flag=wx.ALIGN_CENTER_VERTICAL|wx.LEFT)
        panel.SetSizer(sizer)
        panel.SetMinSize((label_ctrl.GetSize().width+12, self._FIELD_HEIGHT))
        return panel

    def _create_content(self, sizer):
        self._controls = []
        self._create_controls()
        for i, ctrls in enumerate(self._controls):
            row = wx.BoxSizer()
            for x in ctrls:
                if x:
                    row.Add(x)
            flags = wx.ALIGN_LEFT|wx.LEFT|wx.RIGHT
            if i == 0:
                flags |= wx.TOP
            sizer.Add(row, 0, flags, 8)

    def _create_controls(self):
        pass
    
    
class SortingDialog(SFSDialog):
    """Dialog pro volbu parametr� �azen�.

    Metoda 'run()' vrac� specifikaci �azen�, kterou pou��v� formul��
    `pytis.form.LookupForm'.  Je-li dialog opu�t�n jin�m zp�sobem ne� stiskem
    tla��tka, je vr�ceno 'None'.

    """

    _TITLE = _("�azen�")
    _SORT_BUTTON = _("Se�adit")
    _RESET_BUTTON = _("Obnovit v�choz� �azen�")
    _BUTTONS = (_SORT_BUTTON, _RESET_BUTTON) + SFSDialog._BUTTONS
    _COMMIT_BUTTON = _SORT_BUTTON
    
    _DIRECTIONS = (pytis.data.ASCENDENT, pytis.data.DESCENDANT, None)
    _LABELS = {pytis.data.ASCENDENT: _("Vzestupn�"),
               pytis.data.DESCENDANT: _("Sestupn�"),
               None: _("Ne�adit")}
    
    _HELP_TOPIC = 'sorting'
    
    def __init__(self, parent, columns, sorting, direction=None, **kwargs):
        """Initialize the dialog.

        Arguments:

          parent -- wx parent of the dialog window
          columns -- a sequence of 'SFSColumn' instances
          sorting -- current sorting specification in the form of the `sort'
            argument of 'pytis.data.Data.select()'
          direction -- default sorting direction, one of
            'pytis.data.ASCENDENT', 'pytis.data.DESCENDANT'
          kwargs -- passed to the parent class constructor

        """
        self._sorting = sorting
        self._direction = direction
        super(SortingDialog, self).__init__(parent, columns, **kwargs)

    def _create_controls(self):
        choice = self._create_choice
        for cid, dir in self._sorting or ((self._col, self._direction),):
            self._controls.append((
                choice([(c.label(), c) for c in self._columns], selected=self._find_column(cid),
                       tooltip=_("Zvolte sloupec, podle n�j� chcete �adit")),
                choice([(self._LABELS[d], d) for d in self._DIRECTIONS], selected=dir,
                       tooltip=_("Zvolte sm�r �azen�"))))

    def _create_content(self, sizer):
        super(SortingDialog, self)._create_content(sizer)
        button = self._create_button(_("P�idat"), self._on_add,
                                     _("P�idat sloupec sekund�rn�ho �azen�"))
        sizer.Add(button, 0, wx.ALL|wx.CENTER, 5)

    def _customize_result(self, button_wid):
        label = self._button_label(button_wid)
        if label == self._RESET_BUTTON:
            return ()
        elif label != self._SORT_BUTTON:
            return None
        return self._selected_sorting()

    def _selected_sorting(self):
        sorting = []
        for colsel, dirsel in self._controls:
            cid = self._columns[colsel.GetSelection()].id()
            direction = self._DIRECTIONS[dirsel.GetSelection()]
            if direction is not None:
                sorting.append((cid, direction))
        return tuple(sorting)

    def _on_add(self, event):
        new = (self._columns[0].id(), pytis.data.DESCENDANT)
        self._sorting = self._selected_sorting() + (new,)
        self.rebuild()

    
class SFDialog(SFSDialog):
    """Spole�n� z�klad v�ech vyhled�vac�ch a filtrovac�ch dialog�."""

    _OPERATORS = (pytis.data.EQ,
                  pytis.data.NE,
                  pytis.data.LE,
                  pytis.data.GE,
                  pytis.data.LT,
                  pytis.data.GT)
    _LOGICAL_OPERATORS = (pytis.data.AND, pytis.data.OR)
    _WM_OPERATORS = {pytis.data.EQ: pytis.data.WM,
                     pytis.data.NE: pytis.data.NW}
    _LABELS = {pytis.data.EQ: '=',
               pytis.data.NE: '=/=', #u'\u2260',
               pytis.data.LE: '=<',
               pytis.data.GE: '>=',
               pytis.data.LT: '<',
               pytis.data.GT: '>',
               pytis.data.AND: _("AND"),
               pytis.data.OR:  _("OR")}
    # WM and EQ have the same UI ctrl, so we ignore the difference.
    _RELATIONAL_OPERATORS_MAP = {'EQ': pytis.data.EQ,
                                 'NE': pytis.data.NE,
                                 'WM': pytis.data.EQ,
                                 'NW': pytis.data.NE,
                                 'LT': pytis.data.LT,
                                 'LE': pytis.data.LE,
                                 'GT': pytis.data.GT,
                                 'GE': pytis.data.GE}
    _LOGICAL_OPERATORS_MAP = {'AND': pytis.data.AND,
                              'OR': pytis.data.OR}
    _TEXT_CTRL_SIZE = 18
    _NO_COLUMN = SFSColumn('--sfs-dlg-no-column--', pytis.data.String(),
                           '* '+_("hodnota")+' *')
    
    class SFConditionError(Exception):
        def __init__(self, i, ctrl, msg):
            msg = _("Chyba v podm�nce �. %d: %s") % (i+1, msg)
            run_dialog(Error, msg)
            #ctrl.SetFocus()
            #self.focus()
            super(SFDialog.SFConditionError, self).__init__(msg)
            
    def __init__(self, parent, columns, row, condition=None, **kwargs):
        """Initialize the dialog.

        Arguments:

          parent -- wx parent of the dialog window
          columns -- a sequence of 'SFSColumn' instances
          row -- current row as a 'pytis.data.Row' instance or 'None'
          condition -- currently displayed condition as a 'pytis.data.Operator' instance.
          kwargs -- passed to the parent class constructor

        """
        self._row = row
        self._condition = condition
        self._col2_columns = (self._NO_COLUMN,) + tuple(columns)
        super(SFDialog, self).__init__(parent, columns, **kwargs)

    def _strop(self, operator, ):
        if operator.logical():
            op = ' '+ operator.name() +' '
            return '('+ op.join([self._strop(arg) for arg in operator.args()]) + ')'
        else:
            arg1, arg2 = operator.args()
            if isinstance(arg2, (pytis.data.Value, pytis.data.WMValue)):
                if isinstance(arg2.value(), unicode):
                    # Avoid the initial u for unicode strings...
                    arg2 = repr(arg2.value())[1:]
                else:
                    arg2 = repr(arg2.value())
            op = self._LABELS[self._RELATIONAL_OPERATORS_MAP[operator.name()]]
            return arg1 +' '+ op +' '+ arg2

    def _decompose_condition(self, operator, level=1):
        # Decompose nested conditions into a linear list of corresponding relational and logical
        # operators in infix notation.  Hierarchy is represented by the level of logical operators.
        if not isinstance(operator, pytis.data.Operator):
            raise Exception("Invalid condition: "+ repr(operator))
        name, args = operator.name(), operator.args()
        if self._LOGICAL_OPERATORS_MAP.has_key(name):
            op = self._LOGICAL_OPERATORS_MAP[name]
            conds = [self._decompose_condition(arg, level=level+1) for arg in args]
            return reduce(lambda a, b: (a + ((op, level),)) + b, conds)
        elif self._RELATIONAL_OPERATORS_MAP.has_key(name):
            if len(args) != 2:
                raise Exception("Wrong number of arguments: "+ str(args))
            arg1, arg2 = args
            op = self._RELATIONAL_OPERATORS_MAP[name]
            col1 = self._find_column(arg1)
            if col1 is None:
                raise Exception("Invalid column: "+ arg1)
            if isinstance(arg2, str):
                col2 = self._find_column(arg2)
                if col2 is None:
                    raise Exception("Invalid column: "+ arg2)
                value = None
            elif isinstance(arg2, (pytis.data.WMValue, pytis.data.Value)):
                col2 = None
                value = isinstance(arg2, pytis.data.WMValue) \
                        and arg2.value() or arg2.export()
            else:
                raise Exception("Invalid operand type: "+ repr(arg))
            return (op, col1, col2, value),
        else:
            raise Exception("Unsupported operator: "+ name)

    def _create_controls(self):
        choice, spin, label, field, button = self._create_choice, self._create_spin_ctrl, \
            self._create_label, self._create_text_ctrl, self._create_button
        # Construct the ui controls based on the current condition.
        def create_logical_operator(i, n, operator, level):
            return (
                choice([(self._LABELS[op], op) for op in self._LOGICAL_OPERATORS],
                       selected=operator,
                       tooltip=_("Zvolte zp�sob spojen� s p�edchoz�mi podm�nkami")),
                label(_("V�ha oper�toru:")),
                spin(level, length=4, tooltip=_("Zvolte v�hu logick�ho oper�toru.")))
        def create_relational_operator(i, n, operator, col1, col2, value):
            return (
                choice([(c.label(), c) for c in self._columns], selected=col1,
                       on_change=lambda e: self._on_selection_change(i),
                       tooltip=_("Zvolte sloupec tabulky")),
                choice([(self._LABELS[op], op) for op in self._OPERATORS], selected=operator,
                       tooltip=_("Zvolte oper�tor")),
                choice([(c.label(), c) for c in self._col2_columns], selected=col2,
                       on_change=lambda e: self._on_selection_change(i),
                       tooltip=_("Zvolte s ��m m� b�t hodnota porovn�v�na")),
                field(value, length=self._TEXT_CTRL_SIZE,
                      tooltip=_("Zapi�te hodnotu podm�nkov�ho v�razu")),
                button(_("Nas�t"), lambda e: self._on_suck(i),
                       _("Na��st hodnotu aktivn� bu�ky"),
                       enabled=self._row is not None),
                button(_("Vymazat"), lambda e: self._on_clear(i),
                       _("Vymazat obsah podm�nky")),
                button(_("Odebrat"), lambda e: self._on_remove(i),
                       _("Zru�it tuto podm�nku"), enabled=n > 1))
        c = self._find_column(self._col) or self._columns[0]
        empty = pytis.data.EQ(c.id(), pytis.data.Value(c.type(), None))
        #print "===", self._strop(self._condition or empty)
        try:
            operators = self._decompose_condition(self._condition or empty)
        except Exception, e:
            run_dialog(Warning, _("Nepoda�ilo se rozlo�it podm�nkov� v�raz:") +" "+ str(e))
            operators = self._decompose_condition(empty)
        for i, items in enumerate(operators):
            if len(items) == 2:
                self._controls.append(create_logical_operator(i, len(operators), *items))
            else:
                self._controls.append(create_relational_operator(i, len(operators), *items))
                self._on_selection_change(i)
        wval = self._controls[-1][3]
        if wval.IsEnabled():
            self._want_focus = wval

    def _create_content(self, sizer):
        super(SFDialog, self)._create_content(sizer)
        choice, button = self._create_choice, self._create_button
        buttons = [
            button(_("P�idat AND"), lambda e: self._on_add(),
                   tooltip=_("P�idat novou podm�nku v konjunkci (a z�rove�)")),
            button(_("P�idat OR"), lambda e: self._on_add(or_=True),
                   tooltip=_("P�idat novou podm�nku v disjunkci (a nebo)")),
            button(_("Odebrat v�e"), lambda e: self._on_reset(),
                   tooltip=_("Zru�it v�echny st�vaj�c� podm�nky"))]
        bsizer = wx.BoxSizer(wx.HORIZONTAL)
        for b in buttons:
            bsizer.Add(b, 0, wx.RIGHT, 10)
        sizer.Add(bsizer, 0, wx.ALL|wx.CENTER, 5)

    def _selected_condition(self, omit=None):
        # Construct the operator from the current dialog ui controls.
        def logical_operator(i):
            wop, wlabel, wweight = self._controls[i]
            op = self._LOGICAL_OPERATORS[wop.GetSelection()]
            weight = wweight.GetValue()
            return (op, weight)
        def relational_operator(i):
            wcol1, wop, wcol2, wval, b1, b2, b3 = self._controls[i]
            col1 = self._columns[wcol1.GetSelection()]
            op = self._OPERATORS[wop.GetSelection()]
            col2 = self._col2_columns[wcol2.GetSelection()]
            if col2 is not self._NO_COLUMN:
                arg2 = col2.id()
                for basetype in (pytis.data.String, pytis.data.Number, pytis.data.DateTime,
                                 pytis.data.Boolean, pytis.data.Binary):
                    if isinstance(col1.type(), basetype) and not isinstance(col2.type(), basetype):
                        raise self.SFConditionError(i, wcol2, _("Neslu�iteln� typy %s a %s") %
                                                    (col1.type().__class__.__name__,
                                                     col2.type().__class__.__name__))
            elif isinstance(col1.type(), pytis.data.Binary):
                if wval.GetValue():
                    raise self.SFConditionError(i, wval,
                                     _("Bin�rn� sloupec lze testovat pouze na pr�zdnou hodnotu"))
                elif op not in (pytis.data.EQ, pytis.data.NE):
                    raise self.SFConditionError(i, wop,
                                     _("Bin�rn� sloupec lze testovat pouze na rovnost �i nerovnost"))
                arg2 = pytis.data.Value(col1.type(), None)
            else:
                val = wval.GetValue()
                if self._WM_OPERATORS.has_key(op) and (val.find('*') >= 0 or val.find('?') >= 0):
                    op = self._WM_OPERATORS[op]
                    value, err = col1.type().wm_validate(val)
                else:
                    kwargs = dict(strict=False)
                    if isinstance(col1.type(), pytis.data.Boolean):
                        kwargs['extended'] = True
                    value, err = col1.type().validate(val, **kwargs)
                if err:
                    raise self.SFConditionError(i, wval, err.message())
                arg2 = value
            return op(col1.id(), arg2)
        def apply_logical_operator(operator, operators, level):
            # Apply the logical operators at given level to its operands and return the reduced
            # list of top-level operators.
            result = []
            operands = []
            for i in range(1, len(operators), 2):
                op, weight = operators[i]
                operand = operators[i-1]
                if weight == level and op == operator:
                    operands.append(operand)
                else:
                    if operands:
                        operands.append(operand)
                        operand = operator(*operands)
                        operands = []
                    result.extend([operand, (op, weight)])
            op, weight = operators[-2]
            operand = operators[-1]
            if op == operator and weight == level:
                operands.append(operand)
            else:
                result.append(operand)
            if operands:
                result.append(operator(*operands))
            return result
        operators = []
        weights = []
        for i in range(len(self._controls)):
            # Omit the relational operator and the logical operator above, or below for the first
            # operator.
            if omit is None or i not in (omit, (omit == 0 and 1 or omit-1)):
                if i % 2 == 1:
                    op, weight = logical_operator(i)
                    if weight not in weights:
                        weights.append(weight)
                    operators.append((op, weight))
                else:
                    operators.append(relational_operator(i))
        weights.sort()
        weights.reverse()
        for weight in weights:
            operators = apply_logical_operator(pytis.data.AND, operators, weight)
            if len(operators) > 1:
                operators = apply_logical_operator(pytis.data.OR, operators, weight)
        #print "***", self._strop(operators[0])
        assert len(operators) == 1
        return operators[0]

    def _on_selection_change(self, i):
        wcol1, wop, wcol2, wval, bsuck, bclear, bremove = self._controls[i]
        enabled = wcol2.GetSelection() == 0
        wval.Enable(enabled)
        bsuck.Enable(enabled and self._row is not None)

    def _on_clear(self, i):
        wcol1, wop, wcol2, wval = self._controls[i][:4]
        wop.SetSelection(0)
        wcol2.SetSelection(0)
        wval.SetValue('')
        self._on_selection_change(i)

    def _on_suck(self, i):
        wcol1, wop, wcol2, wval = self._controls[i][:4]
        col = self._columns[wcol1.GetSelection()]
        v = self._row[col.id()].export()
        if is_sequence(v):
            v = v[0]
        wval.SetValue(v)

    def _on_remove(self, i):
        try:
            condition = self._selected_condition(omit=i)
        except self.SFConditionError:
            pass
        else:
            self._condition = condition
            self.rebuild()
    
    def _on_add(self, or_=False):
        try:
            condition = self._selected_condition()
        except self.SFConditionError:
            pass
        else:
            op = or_ and pytis.data.OR or pytis.data.AND
            c = self._find_column(self._col) or self._columns[0]
            v = pytis.data.Value(c.type(), None)
            self._condition = op(condition, pytis.data.EQ(c.id(), v))
            self.rebuild()

    def _on_reset(self):
        self._condition = None
        self.rebuild()

            
class SearchDialog(SFDialog):
    """Dialog for manipulation of the current searching condition.

    The 'run()' method of this dialog returns a pair (DIRECTION, CONDITION).
    
    DIRECTION is the selected search direction.  The value can be either
    'pytis.data.FORWARD', 'pytis.data.BACKWARD' or 'None'.  'None' means that
    the search should not be performed (the dialog was escaped), the other two
    values indicate, that next record should be located in given direction.
    
    CONDITION is the selected search condition as a 'pytis.data.Operator'
    instance.

    """
    _NEXT_BUTTON = _("Dal��")
    _PREVIOUS_BUTTON = _("P�edchoz�")
    _BUTTONS = (_NEXT_BUTTON, _PREVIOUS_BUTTON) + SFSDialog._BUTTONS
    _COMMIT_BUTTON = _NEXT_BUTTON    
    _TITLE = _("Hled�n�")
    _HELP_TOPIC = 'searching'

    def __init__(self, *args, **kwargs):
        self._direction = None
        return super(SearchDialog, self).__init__(*args, **kwargs)
    
    def _on_button(self, event):
        mapping = {self._NEXT_BUTTON: pytis.data.FORWARD,
                   self._PREVIOUS_BUTTON: pytis.data.BACKWARD}
        direction = mapping.get(self._button_label(event.GetId()))
        if direction is not None:
            try:
                self._condition = self._selected_condition()
            except self.SFConditionError:
                return
        if direction is not None:
            self._direction = direction
        return super(SearchDialog, self)._on_button(event)
        
    def _customize_result(self, button_wid):
        return self._direction, self._condition


class FilterDialog(SFDialog):
    """Dialog for manipulation of the filtering condition and aggregations.

    This dialog edits the current filtering condition.  In addition it has a
    simple aggregation panel, where the user can display the result of a
    selected aggregation function.  These aggregations work with the data
    filtered by the current selected condition without the need to actually
    perform the filter to the underlying form.

    The 'run()' method of this dialog returns a pair (PERFORM, CONDITION).
    
    PERFORM is a boolean flag indicating whether the CONDITION should be
    applied to the underlying form or not.  It is True when the user presses
    the ``Filter'' or ``Unfilter'' button and False if the user cancels the
    dialog.
    
    CONDITION is the current selected search condition as a
    'pytis.data.Operator' instance or None.  'None' is used when the user
    wishes to unfilter the underlying form.
    
    """
    _FILTER_BUTTON = _("Filtrovat")
    _UNFILTER_BUTTON = _("Zru�it filtr")
    _BUTTONS = (_FILTER_BUTTON, _UNFILTER_BUTTON) + SFSDialog._BUTTONS
    _COMMIT_BUTTON = _FILTER_BUTTON
    _AGG_OPERATORS = (pytis.data.Data.AGG_COUNT,
                      pytis.data.Data.AGG_MIN,
                      pytis.data.Data.AGG_MAX,
                      pytis.data.Data.AGG_SUM,
                      pytis.data.Data.AGG_AVG)
    _AGG_LABELS = {pytis.data.Data.AGG_COUNT: _("Po�et"),
                   pytis.data.Data.AGG_MIN:   _("Minimum"),
                   pytis.data.Data.AGG_MAX:   _("Maximum"),
                   pytis.data.Data.AGG_SUM:   _("Sou�et"), 
                   pytis.data.Data.AGG_AVG:   _("Pr�m�r")}
    _TITLE = _("Filtrov�n�")
    _HELP_TOPIC = 'filtering'

    def __init__(self, parent, columns, row, compute_aggregate, **kwargs):
        """Initialize the dialog.

        Arguments:

          parent -- wx parent of the dialog window
          columns -- a sequence of 'SFSColumn' instances
          row -- current row as a 'pytis.data.Row' instance or 'None'
          compute_aggregate -- a callable object which takes three arguments
            (OPERATION, COLUMN_ID, CONDITION) and returns the result of the
            aggregation OPERATION on COLUMN_ID with given CONDITION as a
            'pytis.data.Value' instance.
          kwargs -- passed to the parent class constructor

        """
        self._compute_aggregate = compute_aggregate
        self._perform = False
        super(FilterDialog, self).__init__(parent, columns, row, **kwargs)

    def _create_content(self, sizer):
        super(FilterDialog, self)._create_content(sizer)
        choice, field, button = self._create_choice, self._create_text_ctrl, self._create_button
        self._agg_controls = (
            choice([(c.label(), c) for c in self._columns],
                   tooltip=_("Zvolte sloupec pro agregaci")),
            choice([(self._AGG_LABELS[op], op) for op in self._AGG_OPERATORS],
                   tooltip=_("Zvolte agrega�n� funkci")),
            field(None, length=24, readonly=True,
                  tooltip=_("Zobrazen� v�sledku agrega�n� funkce")),
            button(_("Zjistit"), self._on_compute_aggregate,
                   tooltip=_("Zobraz v�sledek zvolen� agreka�n� funkce")))
        box = wx.StaticBox(self._dialog, -1, _("Agrega�n� funkce:"))
        boxsizer = wx.StaticBoxSizer(box, wx.HORIZONTAL)
        for ctrl in self._agg_controls:
            boxsizer.Add(ctrl)
        sizer.Add(boxsizer, 0, wx.ALL|wx.CENTER, 5)


    def _on_compute_aggregate(self, event):
        try:
            condition = self._selected_condition()
        except self.SFConditionError:
            pass
        else:
            wcol, wop, wresult, wbutton = self._agg_controls
            op = self._AGG_OPERATORS[wop.GetSelection()]
            col = self._columns[wcol.GetSelection()]
            if op != pytis.data.Data.AGG_COUNT and not isinstance(col.type(), pytis.data.Number):
                # TODO: We should also support Date and maybe other types, but first it must be
                # implemented in the data interface.
                run_dialog(Error, _("Tato operaca nen� pro dan� typ sloupce podporov�na."))
                v = ''
            else:
                result = self._compute_aggregate(op, col.id(), condition)
                if result is not None:
                    v = result.export()
                else:
                    v = ''
            wresult.SetValue(v)

    def _on_button(self, event):
        label = self._button_label(event.GetId())
        if label == self._FILTER_BUTTON:
            try:
                self._condition = self._selected_condition()
            except self.SFConditionError:
                return
            self._perform = True
        elif label == self._UNFILTER_BUTTON:
            self._perform = True
            self._condition = None
        return super(FilterDialog, self)._on_button(event)
        
    def _customize_result(self, button_wid):
        return self._perform, self._condition


def sfs_columns(columns, data, labelfunc=FieldSpec.label):
    """Vra� sloupce vhodn� k�pou�it� v�konstruktorech SFS dialog�.

    (SFS = Search, Filter, Sort)

    Argumenty:

      columns -- sekvence instanc� t��dy 'Column' obsahuj�c� sloupce
      data -- datov� objekt, na n�j� jsou sloupce nav�z�ny
      labelfunc -- funkce jednoho argumentu (instance 'Column') vracej�c�
        n�v�t� sloupce v�dialogu

    """
    sfs_columns = []
    for c in columns:
        label = labelfunc(c)
        if data.find_column(c.id()) is None or not label:
            continue
        id = c.id()
        if not data.permitted(id, pytis.data.Permission.VIEW):
            continue
        type_ = c.type(data)
        sfs_columns.append(SFSColumn(id, type_, label))
    return sfs_columns
