# -*- coding: iso-8859-2 -*-

# Copyright (C) 2006, 2007 Brailcom, o.p.s.
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

from pytis.web import *

_ = lcg.TranslatableTextFactory('pytis')

class UriType(object):
    """URI type for 'uri_provider' 'type' argument."""
    LINK = 'LINK'
    IMAGE = 'IMAGE'

class Link(object):
    """Link representation for 'uri_provider' returned value."""
    def __init__(self, uri, title=None, target=None):
        self._uri = uri
        self._title = title
        self._target = target
    def uri(self):
        return self._uri
    def title(self):
        return self._title
    def target(self):
        return self._target

    
    
class _Field(object):
    """Internal form field representation (all attributes are read-only)."""
    def __init__(self, spec, type, form, uri_provider):
        self.spec = spec
        self.type = type
        self.unique_id = "f%x" % positive_id(self)
        # Duplicate selected specification options for simplified access
        self.id = spec.id()
        self.style = spec.style()
        self.label = spec.label()
        self.column_label = spec.column_label()
        self.label = spec.label()
        self.virtual = spec.virtual()
        # Initialize the formatter at the end.
        self.formatter = FieldFormatter(self, form, uri_provider)

        
class FieldFormatter(object):
    """Field value formatter for read-only fields."""
    
    def __init__(self, field, form, uri_provider):
        """Initialize the instance.

        The aim is to do most of the decision-making and type checking during initialization.
        This speeds up the actual formatting, which can be performed many times.

        """
        self._showform = isinstance(form, ShowForm)
        self._uri_provider = uri_provider
        type = field.type
        if isinstance(type, pytis.data.Boolean):
            self._formatter = self._boolean_formatter
        elif isinstance(type, pytis.data.Password):
            self._formatter = self._password_formatter
        elif isinstance(type, pytis.data.Color):
            self._formatter = self._color_formatter
        elif isinstance(type, pytis.data.Binary):
            self._formatter = self._binary_formatter
        elif type.enumerator():
            self._formatter = self._codebook_formatter
        elif field.spec.filename():
            self._formatter = self._file_formatter
        else:
            self._formatter = self._generic_formatter

    def _boolean_formatter(self, generator, row, field):
        value = row.display(field.id) or row[field.id].value() and _("Yes") or _("No")
        return value, None

    def _color_formatter(self, generator, row, field):
        color = row[field.id].export()
        value = generator.span(color or '&nbsp;', cls="color-value") +' '+ \
                generator.span('&nbsp;', cls="color-display", style="background-color: %s;" %color)
        return value, None
        
    def _binary_formatter(self, generator, row, field):
        buf = row[field.id].value()
        if buf:
            value = buf.filename() or isinstance(type, pd.Image) and _("image") or _("file")
            info = format_byte_size(len(buf))
        else:
            value, info = "", None
        return value, info
    
    def _codebook_formatter(self, generator, row, field):
        value = row[field.id].export()
        display = row.display(field.id)
        info = None
        if display:
            if row.prefer_display(field.id):
                value = display
            elif self._showform:
                info = display
            else:
                value = generator.abbr(value, title=display)
        return value, info
    
    def _password_formatter(self, generator, row, field):
        if self._showform:
            return None, None
        else:
            return self._generic_formatter(generator, row)
        
    def _file_formatter(self, generator, row, field):
        value, info = row[field.id].export(), None
        if value:
            value = row[field.spec.filename()].export()
            info = format_byte_size(len(value))
        return value, None

    def _generic_formatter(self, generator, row, field):
        value = row[field.id].export()
        if value and not isinstance(value, lcg.Localizable):
            value = generator.escape(row.format(field.id))
            lines = value.splitlines()
            if len(lines) > 1:
                if self._showform and field.spec.width(None) is not None:
                    value = generator.textarea(field.id, value=value, readonly=True,
                                               rows=min(len(lines), field.spec.height(), 8),
                                               cols=field.spec.width())
                else:
                    # Insert explicit linebreaks for non-css browasers.
                    value = generator.span(generator.br().join(lines), cls='multiline')
        return value, None

    def format(self, generator, row, field):
        value, info = self._formatter(generator, row, field)
        if value and self._uri_provider:
            src = self._uri_provider(row, field.id, type=UriType.IMAGE)
            if src:
                if info is not None:
                    value += ' ('+ info +')'
                    info = None
                value = generator.img(src, alt=value) #, cls=cls)
            link = self._uri_provider(row, field.id, type=UriType.LINK)
            if link:
                if type(link) in (str, unicode):
                    value = generator.link(value, link)
                else:
                    value = generator.link(value, link.uri(), title=link.title(),
                                           target=link.target())
            if info is not None:
                value += ' ('+ info +')'
        return value    
