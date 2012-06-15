/* -*- coding: utf-8 -*-
 *
 * Copyright (C) 2012 Brailcom, o.p.s.
 * Author: Hynek Hanke
 *
 * This program is free software; you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation; either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

// Remember the base uri of the current script here for later use (hack).
pytis.HtmlField.scripts = document.getElementsByTagName('script');
pytis.HtmlField.base_uri = pytis.HtmlField.scripts[pytis.HtmlField.scripts.length-1].src.replace(/\/[^\/]+$/, '')


pytis.HtmlField.plugin = function(editor) {
    // Construct dialog and add toolbar button
    var types = ['Image', 'Audio', 'Video', 'Resource'];
    editor.addMenuGroup('PytisGroup');
    for (var i=0; i<types.length; i++){
        var type = types[i];
        var ltype = types[i].toLowerCase();
        /* Add dialog */
        CKEDITOR.dialog.add('pytis-attachments-' + ltype, eval('pytis.HtmlField.' + ltype + '_attachment_dialog'));
        /* Add command */
        editor.addCommand('insertPytisAttachment' + type, new CKEDITOR.dialogCommand('pytis-attachments-' + ltype));
        var icon = pytis.HtmlField.base_uri + '/editor-' + ltype + '.png';
        /* Add UI button */
        editor.ui.addButton('PytisAttachment' + type, {
            label: editor.lang.common.image,
            command: 'insertPytisAttachment' + type,
            icon: icon
        });
        /* Add context menu entry */
        if (editor.contextMenu) {
            editor.addMenuItem('editPytisAttachment' + type, {
                label: pytis._('Edit') + ' ' + pytis._(type),
                command: 'insertPytisAttachment' + type,
                group: 'PytisGroup',
                icon: icon
            });

        }
    }
    /* Add a common context menu listener handling all the attachment types */
    editor.contextMenu.addListener(function(element) {
        if (element)
            element = element.getAscendant('a', true);
        if (element && !element.isReadOnly() && !element.data('cke-realelement')){
            for (var i=0; i<types.length; i++){
                if (element.hasClass('lcg-'+types[i].toLowerCase())){
                    var result = {};
                    result['editPytisAttachment'+types[i]] = CKEDITOR.TRISTATE_OFF;
                    return result;
                }
            }
            return null;
        }
    });

}

pytis.HtmlField.attachment_dialog = function(editor, attachment_name, attachment_type, attachment_class, attachment_properties, html_elements) {
    /* Basic attachment dialog for the various types of attachments
     *
     * The dialog can be further modified according to the particular specifics
     * of each attachment type, such as handling additional attachment fields,
     * handling preview and HTML elements input and output.
     *
     * Arguments:
     *  editor ... the editor instance
     *  attachment_name ... name for the attachment type to be used in the UI (should be localized)
     *  attachment_type ... identifier of the attachment type as specified in Pytis (e.g. Image, Video, Resource...)
     *  attachment_class ... CSS class for the top-level HTML element of this object
     *  attachment_properties ... properties of the attachment as passed via the Pytis Attachment API
     *    (e.g. title, description) which should be editable through the dialog. Each listed property
     *    must have a field with the identical id defined in the dialog. Fields 'title' and 'description'
     *    are already defined by this dialog, possible additional fields must be defined by extending this
     *    dialog. See for example the additional thumbnail_size field used in the image dialog).
     *  html_elements ... array of element names for the HTML representation of this object. Each successive
     *    element will be nested in the previous one, so e.g. ['a', 'img'] means an 'img' element nested
     *    in an 'a' element.
     *
     * Return value:
     *  Returns a dictionary description of the dialog for the CKEDITOR.dialog.add factory.
     */

    return {
        minWidth: 600,
        minHeight: 520,
        title: attachment_name,
        contents: [
            // Main Tab
            {id: 'main',
             label: attachment_name,
             elements: [
                 {type : 'hbox',
                  widths : [ '60%', '40%'],
                  height: '150px',
                  children :
                  [
                      {type: 'select',
                       size: 14,
                       id: 'identifier',
                       label: attachment_name,
                       className: 'attachment-selector',
                       items: [],
                       updateAttachmentList: function(element) {
                           // Construct a list of Wiking attachments for this page
                           var field = $(editor.config.pytisFieldId)._pytis_field_instance;
                           var attachments = field.list_attachments()
                           var options = this.getInputElement().$.options
                           // Save field value before options update
                           value = this.getValue();
                           // Update options
                           options.length = 0;
                           for (var i = 0; i < attachments.length; i++) {
                               var a = attachments[i];
                               if (a.type == attachment_type) {
                                   var label = (a.title ? a.title + " (" + a.filename + ")": a.filename);
                                   options.add(new Option(label, a.filename));
                               }
                           }
                           // Restore former value
                           if (value)
                               this.setValue(value);
                       },
                       updatePreview: function(attachment) {
                           // Update preview (to be overriden in children)
                       },
                       onChange: function(element) {
                           var filename = this.getValue();
                           if (filename) {
                               var field = $(editor.config.pytisFieldId)._pytis_field_instance;
                               attachment = field.get_attachment(filename);
                               if (attachment) {
                                   this['attachment'] = attachment;
                                   var dialog = CKEDITOR.dialog.getCurrent();
                                   var fields = attachment_properties;
                                   for (var i = 0; i < fields.length; i++) {
                                       dialog.setValueOf('main', fields[i], attachment[fields[i]]);
                                   }
                                   this.updatePreview(attachment);
                               }
                           }
                       },
                       setup: function(element) {
                           this.updateAttachmentList();
                           // Read identifier from the source
                           var link = element.getAttribute("href");
                           if (link) {
                               var filename = link.match(/\/([^\/]+)$/)[1];
                               if (filename)
                                   this.setValue(filename);
                           }
                       },
                       commit: function(element) {
                           if (this.attachment)
                               element.setAttribute('href', attachment.uri)
                       },
                      },
                      {type: 'html',
                       id: 'preview',
                       html: '',
                      }
                  ]},
                 {type: 'html',
                  id: 'upload-result',
                  html: '<div id="ckeditor-upload-result"></div>'
                 },
                 {type : 'hbox',
                  children :
                  [
                      {type: 'file',
                       id: 'upload',
                       label: editor.lang.image.btnUpload,
                       style: 'height:50px',
                       setup: function(element) {
                           // Register onload hook to respond to upload actions
                           var frame = CKEDITOR.document.getById(this._.frameId);
                           // We need to unregister each event listener first to registering it multiple times
                           this.removeListener('formLoaded', this.onFormLoaded);
                           this.on('formLoaded', this.onFormLoaded, this);
                           frame.removeListener('load', this.onIFrameLoaded);
                           frame.on('load', this.onIFrameLoaded, this);
                       },
                       onFormLoaded: function() {
                           var field = $(editor.config.pytisFieldId)._pytis_field_instance;
                           var frameDocument = CKEDITOR.document.getById(this._.frameId).getFrameDocument();
                           if (frameDocument.$.forms.length > 0) {
                               /* This is a little tricky as the file upload
                                * form is inside an IFRAME.  It is not possible
                                * to submit the AttachmentStorage request
                                * through AJAX due to certain browser
                                * limitations so it is submitted within the
                                * iframe.  We must copy all hidden form fields
                                * from the main edited form to mimic the
                                * bahavior of pytis form AJAX updates and to get
                                * the uploaded data within the Python code in
                                * 'EditForm._attachment_storage_insert()'.
                                */
                               var form = frameDocument.$.forms[0];
                               field._file_upload_form = form;
                               if (form.getAttribute('action') != field._form.getAttribute('action')) {
                                   form.setAttribute('action', field._form.getAttribute('action'));
                                   hidden_fields = {'_pytis_form_update_request': 1,
                                                    '_pytis_attachment_storage_field': field._id,
                                                    '_pytis_attachment_storage_request': 'insert'};
                                   for (var i = 0; i < field._form.elements.length; i++) {
                                       var e = field._form.elements[i];
                                       if (e.type == 'hidden') // && e.name != 'submit')
                                           hidden_fields[e.name] = e.value;
                                   }
                                   for (var name in hidden_fields) {
                                       Element.insert(form, new Element('input',
                                                                        {'type': 'hidden',
                                                                         'name': name,
                                                                         'value': hidden_fields[name]}));
                                   }
                               }
                           }
                       },
                       onIFrameLoaded: function() {
                           var dialog = CKEDITOR.dialog.getCurrent();
                           var body_childs = $(this._.frameId).contentWindow.document.body.childNodes;
                           if ((body_childs.length == 1) && (body_childs[0].tagName.toLowerCase() == 'pre')){
                               // This is a JSON reply
                               var reply = body_childs[0].innerHTML.evalJSON();
                               var msg, cls;
                               dialog.getContentElement('main', 'identifier').updateAttachmentList();
                               dialog.getContentElement('main', 'upload').reset();
                               if (reply['success'] == true){
                                   msg = pytis._("Upload successful");
                                   cls = "ckeditor-success";
                               }else{
                                   msg = pytis._("Error: ") + reply['message'];
                                   cls = "ckeditor-error";
                               }
                               $('ckeditor-upload-result').update("<p class=\""+cls+"\">"+msg+"</p>");
                           }
                       }
                      },
                      {type: 'fileButton',
                       filebrowser: 'upload:filename',
                       label: pytis._("Add"),
                       'for': ['main', 'upload'],
                       onClick: function() {
                           var field = $(editor.config.pytisFieldId)._pytis_field_instance;
                           // We can't simply call form.submit(), because Wiking
                           // uses a hidden field named 'submit' for its internal
                           // purposes and this hidden field masks the submit method
                           // (not really clever...).
                           var result = document.createElement('form').submit.call(field._file_upload_form);
                       }
                      },
                  ]
                 },
                 {type: 'text',
                  id: 'title',
                  label: pytis._('Title'),
                  commit: function(element) {
                      element.setText(this.getValue());
                  },
                 },
                 {type: 'text',
                  id: 'description',
                  label: pytis._('Description'),
                  commit: function(element) {
                      element.setAttribute('alt', this.getValue());
                  },
                 },
             ]},
        ],
        onShow: function() {
            // Check if editing an existing element or inserting a new one
            var sel = editor.getSelection();
            var element = sel.getStartElement();
            if (element)
                element = element.getAscendant(html_elements[0], true);
            if (!element || element.getName() != html_elements[0] || element.data('cke-realelement') || !element.hasClass(attachment_class)) {
                // The element doesn't exist yet, create it together with all its descendants
                element = editor.document.createElement(html_elements[0]);
                element.addClass(attachment_class);
                var parent = element;
                for (var i=1; i<html_elements.length; i++){
                    var child = editor.document.createElement(html_elements[1]);
                    parent.append(child);
                    parent = child;
                }
                this.insertMode = true;
            }
            else
                this.insertMode = false;
            this.element = element;
            this.setupContent(this.element);
        },
        onOk: function(element) {
            // Update attachment attributes
            var dialog = CKEDITOR.dialog.getCurrent();
            var filename = dialog.getValueOf('main', 'identifier')
            var field = $(editor.config.pytisFieldId)._pytis_field_instance;
            attributes = {}
            for (var i=0; i<=attachment_properties.length; i++)
                attributes[attachment_properties[i]] = dialog.getValueOf('main', attachment_properties[i]);
            var error = field.update_attachment(filename, attributes); // TODO: Display error message when error != null.
            // Insert or update the HTML element
            if (this.insertMode){
                editor.insertElement(this.element);
            }
            this.commitContent(this.element);
        },
    };
};

ck_element = function(dialog, id) {
    /* Helper function to address a particular element in dialog definition by its id
     *
     * The function searches element definitions by their id among the elements
     * of the first dialog tab. It also searches for childern inside any 'hbox'
     * and 'vbox' containers.
     *
     * Arguments:
     *  dialog ... the dialog to search for the element
     *  id  ... id of the element
     *
     * Return value:
     *  Returns the element or nul if none is found
     */
    ck_get_element_from_list = function (elements, id) {
        for (var i = 0; i < elements.length; i++) {
            if (elements[i].id == id){
                return elements[i];
            }
            else if (elements[i].type == 'hbox' || elements[i].type == 'vbox'){
                var el = ck_get_element_from_list(elements[i].children, id)
                if (el)
                    return el;
            }
        }
        return null;
    }
    var elements = dialog['contents'][0]['elements'];
    return ck_get_element_from_list(elements, id);
}

pytis.HtmlField.image_attachment_dialog = function(editor) {

    dialog = pytis.HtmlField.attachment_dialog(
        editor, pytis._("Image"), 'Image', "lcg-image",
        ['title', 'description', 'thumbnail_size'],
        ['a', 'img']);

    ck_element(dialog, 'identifier').updatePreview = function(attachment) {
        if (attachment){
            if (attachment.thumbnail)
                $('image-preview').src = attachment.thumbnail.uri;
            else
                $('image-preview').src = attachment.uri;
            $('image-preview').alt = attachment.description;
        }
    }

    ck_element(dialog, 'identifier').setup = function(element) {
        this.updateAttachmentList();
        // Read identifier from the image link
        var img = element.getFirst();
        if (img) {
            var link = img.getAttribute("src");
            if (link) {
                var filename = link.match(/\/([^\/]+)\?/)[1];
                if (filename)
                    this.setValue(filename);
            }
        }
    }

    ck_element(dialog, 'identifier').commit = function(element) {
        var attachment = this.attachment;
        if (attachment) {
            var uri;
            if (attachment.thumbnail)
                uri = attachment.thumbnail.uri;
            else
                uri = attachment.uri;
            var img = element.getFirst();
            img.setAttribute('src', uri);
        }
    }

    ck_element(dialog, 'preview').html = '<div class="preview-container"><img id="image-preview" src="" alt="" /></div>';

    ck_element(dialog, 'title').commit = function(element) {
        var img = element.getFirst()
        img.setAttribute('title', this.getValue());
    }

    ck_element(dialog, 'description').commit = function(element) {
        var img = element.getFirst()
        img.setAttribute('alt', this.getValue());
    }

    dialog['contents'][0].elements = dialog['contents'][0].elements.concat([
        {type: 'select',
         id: 'thumbnail_size',
         label: pytis._('Preview size'),
         items: [[pytis._('Full'), 'full'],
                 [pytis._('Small'), 'small'],
                 [pytis._('Medium'), 'medium'],
                 [pytis._('Large'), 'large']]},
        {type: 'select',
         id: 'align',
         label: pytis._('Align'),
                  items: [[pytis._('Left'), 'left'], [pytis._('Right'), 'right']],
         setup: function(element) {
             // Read alignment of the image
             var img = element.getFirst();
             if (img)
                 this.setValue(img.getAttribute('align'));
         },
         commit: function(element) {
             // Set image alignment
             var img = element.getFirst();
             img.setAttribute('align', this.getValue());
         }
        },
        {type : 'hbox',
         widths : [ '20%', '80%'],
         children :
         [
             {type: 'select',
              id: 'link-type',
              label: pytis._('Link'),
              items: [[pytis._('Original'), 'original', 'original-link'],
                      [pytis._('Anchor inside page'), 'anchor', 'anchor-link'],
                               [pytis._('External link'), 'external', 'external-link']],
              setup: function(element) {
                  if (element.hasClass('original-link'))
                      this.setValue('original');
                  else if (element.hasClass('anchor-link'))
                      this.setValue('anchor');
                  else if (element.hasClass('external-link'))
                      this.setValue('external');
                  else {
                      // Handle cases where type is not specified
                      var link = element.getValue('href');
                      if (link && link.length > 0)
                          this.setValue('external');
                      else
                          this.setValue('original');
                  }
                  this.onChange(element);
              },
              commit: function(element) {
                  // Remove all link type classes from element and add the new class
                  for (var i = 0; i < this.items.length; i++) {
                      var val = this.items[i][1];
                      var cls = this.items[i][2];
                      if (val == this.getValue()) {
                          if (!element.hasClass(cls))
                              element.addClass(cls);
                      } else {
                          if (element.hasClass(cls))
                              element.removeClass(cls);
                      }
                  }
                  // Handle the 'original' type of link
                  if (this.getValue() == 'original') {
                      var attachment = this.attachment;
                      if (attachment) {
                          element.setAttribute('rel', "lightbox[gallery]");
                          element.setAttribute('href', attachment.uri);
                      }
                  }
                  // Values for other types of links are handled in the corresponding fields
              },
              onChange: function(element) {
                  var dialog = CKEDITOR.dialog.getCurrent();
                  var fields = ['anchor-link', 'external-link'];
                  for (var i = 0; i < fields.length; i++) {
                      var image = dialog.getContentElement('main',  fields[i]);
                      image.getElement().getParent().hide();
                  }
                  if (this.getValue() == 'anchor') {
                      var image = dialog.getContentElement('main',  'anchor-link');
                      image.getElement().getParent().show();
                  }
                  if (this.getValue() == 'external') {
                      var image = dialog.getContentElement('main',  'external-link');
                      image.getElement().getParent().show();
                  }
              }
             },
             {type: 'select',
              id: 'anchor-link',
              label: pytis._('Link to anchor'),
              items: [],
              onShow: function (element) {
                  // Construct a list of anchors in this page
                  var anchorList = new CKEDITOR.dom.nodeList(editor.document.$.anchors);
                  options = this.getInputElement().$.options;
                           options.length = 0;
                  for (var i = 0, count = anchorList.count(); i < count; i++) {
                      var item = anchorList.getItem(i);
                      options.add(new Option(item.getText() + " (" + item.getAttribute('name') + ")", item.getAttribute('name')));
                  }
              },
              setup: function(element) {
                  var dialog = CKEDITOR.dialog.getCurrent();
                  if (dialog.getValueOf('main', 'link-type') == 'anchor') {
                      var link = element.getAttribute("href");
                      if (link.substr(0, 1) == "#") {
                          this.setValue(link.substr(1));
                      }
                  }
              },
              commit: function(element) {
                  var dialog = CKEDITOR.dialog.getCurrent();
                  if (dialog.getValueOf('main', 'link-type') == 'anchor') {
                      element.setAttribute("href", "#" + this.getValue());
                  }
              }
             },
             {type: 'text',
              id: 'external-link',
              label: pytis._('External link'),
                       setup: function(element) {
                           var dialog = CKEDITOR.dialog.getCurrent();
                           if (dialog.getValueOf('main', 'link-type') == 'external') {
                               this.setValue(element.getAttribute("href"));
                           }
                       },
              commit: function(element) {
                  var dialog = CKEDITOR.dialog.getCurrent();
                  if (dialog.getValueOf('main', 'link-type') == 'external')
                      element.setAttribute('href', this.getValue());
              }
             },
         ]}]);
    return dialog;
}

pytis.HtmlField.audio_attachment_dialog = function(editor) {

    dialog = pytis.HtmlField.attachment_dialog(
        editor, pytis._("Audio"), 'Audio', "lcg-audio",
        ['title', 'description'],
        ['a']);

    ck_element(dialog, 'identifier').updatePreview = function(attachment) {
        if (attachment) {
            var flashvars = {'file': attachment.uri};
            var player_uri = '/_resources/flash/mediaplayer.swf';
            embed_swf_object(player_uri, 'audio-preview', 400, 400, flashvars, '9', '<p>Flash not available</p>', true);
        }
    }

    ck_element(dialog, 'preview').html = '<div class="preview-container"><div id="audio-preview"></div>';

    return dialog;
}

pytis.HtmlField.video_attachment_dialog = function(editor) {

    dialog = pytis.HtmlField.attachment_dialog(
        editor, pytis._("Video"), 'Video', "lcg-video",
        ['title', 'description'],
        ['a']);

    ck_element(dialog, 'identifier').updatePreview = function(attachment) {
        if (attachment) {
            var flashvars = {'file': attachment.uri};
            var player_uri = '/_resources/flash/mediaplayer.swf';
            embed_swf_object(player_uri, 'video-preview', 400, 400, flashvars, '9', '<p>Flash not available</p>', true);
        }
    }

    ck_element(dialog, 'preview').html = '<div class="preview-container"><div id="video-preview"></div></div>';

    return dialog;
}

pytis.HtmlField.resource_attachment_dialog = function(editor) {

    dialog = pytis.HtmlField.attachment_dialog(
        editor, pytis._("Attachment"), 'Resource', "lcg-resource",
        ['title', 'description'],
        ['a']);

    return dialog;
}

pytis.HtmlField.on_dialog = function(event) {
    if (event.data.name == 'link') {
        event.data.definition.removeContents('advanced');
        event.data.definition.removeContents('target');
    }
};

