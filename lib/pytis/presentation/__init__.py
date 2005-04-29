# -*- coding: iso-8859-2 -*-

# Transformace a prezentace dat
# 
# Copyright (C) 2002, 2005 Brailcom, o.p.s.
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

"""Transformace a prezentace dat.

Tento modul m� za �kol �e�it zpracov�n� dat, kter� nep��slu�� ani modulu
'pytis.data' ani konkr�tn� podob� u�ivatelsk�ho rozhran�.  Typick�mi funkcemi
tohoto modulu jsou po��t�n� hodnot \"virtu�ln�ch\" pol��ek, p�evod hodnot
r�zn�ho druhu do stringov� podoby nebo form�tov�n� stringov�ho textu.

"""

from spec import *
from field import *

for file in (spec, field):
    file.__dict__.update(globals())
