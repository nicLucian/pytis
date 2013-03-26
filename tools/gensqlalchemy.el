;;; gensqlalchemy.el --- support for working with pytis database specifications

;; Copyright (C) 2012, 2013 Brailcom, o.p.s.

;; COPYRIGHT NOTICE

;; This program is free software; you can redistribute it and/or modify
;; it under the terms of the GNU General Public License as published by
;; the Free Software Foundation; either version 3 of the License, or
;; (at your option) any later version.

;; This program is distributed in the hope that it will be useful,
;; but WITHOUT ANY WARRANTY; without even the implied warranty of
;; MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
;; GNU General Public License for more details.

;; You should have received a copy of the GNU General Public License
;; along with this program.  If not, see <http://www.gnu.org/licenses/>.


;; This file defines gensqlalchemy-mode which is a minor mode for working with
;; gensqlalchemy database specifications.  Although it is a common minor mode,
;; it makes sense only in Python major modes.

;; To enable the mode automatically in database specifications, you may want to
;; add the following lines to your Python mode hook function:
;;
;;   (when (and (buffer-file-name)
;;              (string-match "/db/dbdefs/" (buffer-file-name)))
;;     (gensqlalchemy-mode 1))
;;
;; Or you can enable it manually with `M-x gensqlalchemy-mode'.

;; The mode binds its commands to key sequences starting with prefix `C-c C-q'.
;; You can type `C-c C-q C-h' to get overview of the available key bindings.

;; The most basic command is `C-c C-q C-q' (`gensqlalchemy-eval') which creates
;; and displays the SQL code of the current specification object.  Its variant
;; `C-c C-q a' (`gensqlalchemy-add') adds the definition to already created SQL
;; code, this way you can compose an SQL update file for several objects.  With
;; a prefix argument the commands generate SQL code also for objects depending
;; on the current definition.  You can display the current SQL code anytime
;; using `C-c C-q s' (`gensqlalchemy-show-sql-buffer').

;; gensqlalchemy.el uses standard Emacs sql-mode means for communication with
;; the database.  To be able to work with a database, you must first create a
;; corresponding SQL buffer using standard Emacs commands such as
;; `M-x sql-postgres'.  gensqlalchemy then asks for that buffer name when it
;; needs to communicate with the database.

;; Once a database connection is available, you can test the generated SQL code
;; with `C-c C-q t' (`gensqlalchemy-test').  The code is executed in a separate
;; transaction and rollbacked afterwards.  gensqlalchemy.el actually never
;; changes the database itself, everything is executed in discarded
;; transactions.  Nevertheless you should always be careful and not to use
;; gensqlalchemy.el interactions on production databases.

;; You can view current object definition in the database using `C-c C-q d'
;; (`gensqlalchemy-show-definition').  With a prefix argument new definition of
;; the object is inserted into the database into a separate schema and then
;; displayed; it's some form of pretty formatting the SQL code and accompanying
;; it with additional information.  You can compare the original and new
;; definitions anytime using `C-c C-q =' (`gensqlalchemy-compare').  When you
;; want to view the changes in Ediff, use a prefix argument.  Note that the new
;; definition is put into a separate schema again.  You can also compare SELECT
;; outputs of new views and functions using `C-c C-q o'
;; (`gensqlalchemy-compare-outputs').

;; You can list all objects dependent on the current specification using
;; `C-c C-q i' (`gensqlalchemy-info').  The list includes source locations you
;; can visit by pressing RET or clicking on them.

;; Whenever you meet an error during gsql SQL conversion, you can use
;; `M-x gensqlalchemy-show-buffer' command to display the corresponding source
;; in specifications.  Some gensqlalchemy.el functions can do that for you
;; automatically when such an error occurs on their invocation.

;; When editing specifications of SQL or PL/pgSQL database functions stored in
;; external .sql files, you can directly jump to the given file with the
;; command `C-c C-q f' (`gensqlalchemy-sql-function-file').  After editing and
;; saving it you can kill the buffer and window with `C-x 4 0'.

;; The mode comes with reasonable default settings, but you may want to
;; customize them using `M-x customize-group RET gensqlalchemy RET'.  The most
;; important option is `gensqlalchemy-gsql' which needs to be set if gsql
;; utility is not present in standard PATH.


(require 'cl)
(require 'compile)
(require 'python)
(require 'sql)

(defgroup gensqlalchemy nil
  "Emacs support for gensqlalchemy editing."
  :group 'python)

(defcustom gensqlalchemy-gsql "gsql"
  "gsql binary."
  :group 'gensqlalchemy
  :type 'string)

(defcustom gensqlalchemy-pretty-output-level 1
  "Value for `--pretty' gsql command line option."
  :group 'gensqlalchemy
  :type 'integer)

(defcustom gensqlalchemy-temp-schema (format "%s_temp" user-login-name)
  "Schema to use for SQL code testing."
  :group 'gensqlalchemy
  :type 'string)

(defcustom gensqlalchemy-temp-directory (concat temporary-file-directory "gensqlalchemy-el/")
  "Directory to use for storing miscellaneous temporary files."
  :group 'gensqlalchemy
  :type 'directory)

(defcustom gensqlalchemy-default-line-limit 1000
  "Default LIMIT value in SELECT commands performed by SQLAlchemy."
  :group 'gensqlalchemy
  :type 'integer)

(defvar gensqlalchemy-specification-directory "dbdefs")
(defvar gensqlalchemy-common-directories '("lib" "db"))

(define-minor-mode gensqlalchemy-mode
  "Toggle gensqlalchemy mode.
Currently the mode just defines some key bindings."
  nil " gsql" '(("\C-c\C-qe" . gensqlalchemy-eval)
                ("\C-c\C-q\C-q" . gensqlalchemy-eval)
                ("\C-c\C-qa" . gensqlalchemy-add)
                ("\C-c\C-qd" . gensqlalchemy-show-definition)
                ("\C-c\C-qf" . gensqlalchemy-sql-function-file)
                ("\C-c\C-qi" . gensqlalchemy-info)
                ("\C-c\C-qo" . gensqlalchemy-compare-outputs)
                ("\C-c\C-qs" . gensqlalchemy-show-sql-buffer)
                ("\C-c\C-qt" . gensqlalchemy-test)
                ("\C-c\C-q=" . gensqlalchemy-compare)
                ))

(defun gensqlalchemy-sql-mode ()
  (unless (eq major-mode 'sql-mode)
    (sql-mode)
    (sql-set-product 'postgres)))

(defun gensqlalchemy-specification-directory (buffer &optional require)
  (let ((directory (with-current-buffer (or buffer (current-buffer))
                     (directory-file-name default-directory))))
    (while (and (not (string= directory "/"))
                (not (string= (file-name-nondirectory directory) gensqlalchemy-specification-directory)))
      (setq directory (directory-file-name (file-name-directory directory))))
    (when (and require (string= directory "/"))
      (error "Specification directory not found"))
    (file-name-directory directory)))
  
(defun gensqlalchemy-buffer-name (ext &optional buffer)
  (let ((directory (directory-file-name (gensqlalchemy-specification-directory buffer)))
        name)
    (while (member (file-name-nondirectory directory) gensqlalchemy-common-directories)
      (setq directory (directory-file-name (file-name-directory directory))))
    (setq name (file-name-nondirectory directory))
    (when (string= name "")
      (setq name gensqlalchemy-specification-directory))
    (format "*%s:%s*" name ext)))

(defmacro with-gensqlachemy-specification (&rest body)
  (let (($spec-regexp (gensym))
        ($point (gensym)))
    `(save-excursion
       (let ((,$spec-regexp "^class +\\([a-zA-Z_0-9]+\\) *("))
         (goto-char (line-beginning-position))
         (unless (or (looking-at ,$spec-regexp)
                     (re-search-backward ,$spec-regexp nil t)
                     (re-search-forward ,$spec-regexp nil t))
           (error "No specification found around point"))
         (goto-char (line-beginning-position))
         (let ((specification-name (match-string-no-properties 1))
               (,$point (point)))
           (forward-char)
           (unless (re-search-forward ,$spec-regexp nil t)
             (goto-char (point-max)))
           (save-restriction
             (narrow-to-region ,$point (point))
             (goto-char ,$point)
             ,@body))))))

(defun gensqlalchemy-specification ()
  (with-gensqlachemy-specification
    specification-name))

(defun gensqlalchemy-temp-file (file-name)
  (concat gensqlalchemy-temp-directory file-name))

(defun gensqlalchemy-empty-file (file-name)
  (= (or (nth 7 (file-attributes file-name)) 0) 0))
  
(defun gensqlalchemy-prepare-output-buffer (base-buffer erase)
  (let ((directory (gensqlalchemy-specification-directory base-buffer t))
        (buffer (gensqlalchemy-buffer-name "sql" base-buffer)))
    (with-current-buffer (get-buffer-create buffer)
      (when erase
        (erase-buffer))
      (gensqlalchemy-sql-mode)
      (setq default-directory directory))
    buffer))

(defun gensqlalchemy-run-gsql (&rest args)
  (apply 'call-process gensqlalchemy-gsql nil t nil args))

(defun gensqlalchemy-send-buffer ()
  "Send the buffer contents to the SQL process via file.
This is useful for longer inputs where the input may break in comint."
  (let ((file (gensqlalchemy-temp-file "input")))
    (write-region (point-min) (point-max) file)
    (sql-send-string (concat "\\i " file))))

(defun gensqlalchemy-eval (&optional dependencies)
  "Convert current specification to SQL and display the result.
If called with a prefix argument then show dependent objects as well."
  (interactive "P")
  (let ((buffer (gensqlalchemy-display t dependencies nil)))
    (when buffer
      (pop-to-buffer buffer))))

(defun gensqlalchemy-add (&optional dependencies)
  "Convert current specification to SQL and add it to the displayed SQL.
If called with a prefix argument then show dependent objects as well."
  (interactive "P")
  (let ((buffer (gensqlalchemy-display nil dependencies nil)))
    (when buffer
      (pop-to-buffer buffer))))

(defun gensqlalchemy-display (erase dependencies schema)
  (let* ((spec-name (gensqlalchemy-specification))
         (output-buffer (gensqlalchemy-prepare-output-buffer (current-buffer) erase))
         (args (append (list (format "--pretty=%d" gensqlalchemy-pretty-output-level))
                       (unless dependencies
                         '("--no-deps"))
                       (when schema
                         (list (concat "--schema=" schema)))
                       (list (format "--limit=^%s$" spec-name)
                             gensqlalchemy-specification-directory))))
    (save-some-buffers)
    (with-current-buffer output-buffer
      (unless (or erase
                  (string= "" (buffer-substring-no-properties (point-min) (point-max))))
        (goto-char (point-max))
        (insert "\n"))
      (when schema
        (insert (format "create schema %s;\n" gensqlalchemy-temp-schema)))
      (apply 'gensqlalchemy-run-gsql args)
      (if (search-backward "Traceback (most recent call last):" nil t)
          (progn
            (pop-to-buffer output-buffer)
            (goto-char (point-max))
            (gensqlalchemy-show-error)
            nil)
        output-buffer))))
  
(defun gensqlalchemy-show-sql-buffer ()
  "Show the buffer with converted SQL output."
  (interactive)
  (let ((buffer (get-buffer (gensqlalchemy-buffer-name "sql"))))
    (when buffer
      (pop-to-buffer buffer))))

(defmacro with-gensqlalchemy-sql-buffer (buffer &rest body)
  (let (($buffer buffer))
    `(with-current-buffer ,$buffer
       (unless sql-buffer
         (sql-set-sqli-buffer))
       ,@body)))

(defmacro with-gensqlalchemy-rollback (&rest body)
  (let (($buffer (gensym)))
    `(let ((,$buffer (if (eq major-mode 'sql-mode)
                         (current-buffer)
                       (get-buffer (gensqlalchemy-buffer-name "sql")))))
       (when ,$buffer
         (with-gensqlalchemy-sql-buffer ,$buffer
           (sql-send-string "begin;")
           (unwind-protect (progn ,@body)
             (with-current-buffer ,$buffer
               (sql-send-string "rollback;"))))))))

(defmacro with-gensqlalchemy-log-file (file-name &rest body)
  `(progn
     (unless (file-exists-p gensqlalchemy-temp-directory)
       (make-directory gensqlalchemy-temp-directory))
     (sql-send-string (concat "\\o " ,file-name))
     ,@body
     (sql-send-string "\\o")))

(defun gensqlalchemy-wait-for-outputs (sql-buffer)
  (let ((terminator "gensqlalchemy-el-terminator")
        (n 100))
    (with-current-buffer sql-buffer
      (let ((point (point-max)))
        (goto-char point)
        (sql-send-string (format "select '%s';" terminator))
        (while (and (> n 0) (not (re-search-forward terminator nil t)))
          (decf n)
          (sit-for 0.1)
          (goto-char point))))))

(defun gensqlalchemy-current-objects (&optional schema)
  (let ((spec-name (gensqlalchemy-specification))
        (objects '()))
    (with-temp-buffer
      (setq default-directory (gensqlalchemy-specification-directory nil t))
      (apply 'gensqlalchemy-run-gsql
             (append (list "--names" "--no-deps" (format "--limit=^%s$" spec-name))
                     (when schema
                       (list (concat "--schema=" schema)))
                     (list gensqlalchemy-specification-directory)))
      (goto-char (point-min))
      (while (looking-at "^\\([-a-zA-Z]+\\) \\([^(\n]*\\)\\((.*)\\)?$")
        (push (list (match-string 1) (match-string 2) (match-string 3)) objects)
        (goto-char (line-beginning-position 2))))
    objects))

(defvar gensqlalchemy-psql-def-commands
  '(("FUNCTION" . "\\sf+")
    ("SCHEMA" . "\\dn+")
    ("SEQUENCE" . "\\ds+")
    ("TABLE" . "\\d+")
    ("TYPE" . "\\dT+")
    ("VIEW" . "\\d+")))
(defun gensqlalchemy-definition (file-name &optional send-buffer schema)
  (let ((objects (gensqlalchemy-current-objects schema))
        (output-buffer nil))
    (with-gensqlalchemy-rollback
      (when send-buffer
        (with-gensqlalchemy-sql-buffer send-buffer
          (gensqlalchemy-send-buffer)))
      (sql-send-string "set search_path to public;")
      (with-gensqlalchemy-log-file file-name
        (mapc #'(lambda (spec)
                  (destructuring-bind (kind name args) spec
                    (let ((command (cdr (assoc kind gensqlalchemy-psql-def-commands))))
                      (when command
                        (setq output-buffer sql-buffer)
                        (when args
                          (setq name (concat name (replace-regexp-in-string "[^(),]+::" "" args))))
                        (sql-send-string (format "%s %s" command name))))))
              objects)))
    output-buffer))

(defun gensqlalchemy-show-definition (&optional arg)
  "Show database definition of the current specification.
With an optional prefix argument show new definition of the specification."
  (interactive "P")
  (let ((file (gensqlalchemy-temp-file "def"))
        (buffer (and arg (gensqlalchemy-display t nil gensqlalchemy-temp-schema)))
        (schema (and arg gensqlalchemy-temp-schema)))
    (unless (and arg (not buffer))
      (gensqlalchemy-wait-for-outputs (gensqlalchemy-definition file buffer schema))
      (if (gensqlalchemy-empty-file file)
          (message "Definition not found")
        (let ((buffer (get-buffer-create (gensqlalchemy-buffer-name "def"))))
          (pop-to-buffer buffer)
          (erase-buffer)
          (insert-file-contents file))))))

(defun gensqlalchemy-test ()
  "Try to run SQL commands from SQL output buffer.
The commands are wrapped in a transaction which is aborted at the end."
  (interactive)
  (with-gensqlalchemy-rollback
    (gensqlalchemy-send-buffer)))

(defun gensqlalchemy-compare (&optional arg)
  "Compare current specification with the definition in the database.
With an optional prefix argument show the differences in Ediff."
  (interactive "P")
  (let ((buffer (gensqlalchemy-display t nil gensqlalchemy-temp-schema))
        (old-def-file (gensqlalchemy-temp-file "olddef"))
        (new-def-file (gensqlalchemy-temp-file "newdef")))
    (when buffer
      (gensqlalchemy-definition old-def-file)
      (gensqlalchemy-definition new-def-file buffer gensqlalchemy-temp-schema)
      (gensqlalchemy-wait-for-outputs (with-current-buffer buffer sql-buffer))
      (if arg
          (ediff-files old-def-file new-def-file)
        (diff old-def-file new-def-file "-u")))))

(defvar gensqlalchemy-last-function-arguments nil)
(defun gensqlalchemy-select (object file n use-last-arguments order-by)
  (destructuring-bind (kind name args) object
    (unless (member kind '("TABLE" "VIEW" "FUNCTION"))
      (error "Unable to run SELECT on %s" kind))
    (let ((command (concat "SELECT * FROM " name)))
      (when args
        (unless use-last-arguments
          (setq gensqlalchemy-last-function-arguments
                (read-string (format "Function arguments %s: " args)
                             gensqlalchemy-last-function-arguments)))
        (setq command (concat command "(" gensqlalchemy-last-function-arguments ")")))
      (unless (string= order-by "")
        (setq command (concat command " ORDER BY " order-by)))
      (when n
        (setq command (concat command " LIMIT " (number-to-string n))))
      (setq command (concat command ";"))
      (with-gensqlalchemy-log-file file
        (sql-send-string command)))))

(defvar gensqlalchemy-last-order-by "")
(defun gensqlalchemy-compare-outputs (&optional n)
  "Compare SELECT outputs of the original and new definition.
By default compare at most `gensqlalchemy-default-line-limit' lines of output.
With a numeric prefix argument compare that many lines of output.
With a universal prefix argument compare complete outputs."
  (interactive "P")
  (cond
   ((null n)
    (setq n gensqlalchemy-default-line-limit))
   ((consp n)
    (setq n nil)))
  (when (and (numberp n) (< n 0))
    (setq n 0))
  (let ((old-object (car (gensqlalchemy-current-objects)))
        (new-object (car (gensqlalchemy-current-objects gensqlalchemy-temp-schema)))
        (old-data-file (gensqlalchemy-temp-file "olddata"))
        (new-data-file (gensqlalchemy-temp-file "newdata"))
        (new-buffer (gensqlalchemy-display t nil gensqlalchemy-temp-schema)))
    (when new-buffer
      (setq gensqlalchemy-last-order-by
            (read-string "Order by: " gensqlalchemy-last-order-by))
      (with-gensqlalchemy-rollback
        (gensqlalchemy-select old-object old-data-file n nil gensqlalchemy-last-order-by))
      (with-gensqlalchemy-rollback
        (with-gensqlalchemy-sql-buffer new-buffer
          (gensqlalchemy-send-buffer))
        (gensqlalchemy-select new-object new-data-file n t gensqlalchemy-last-order-by))
      (gensqlalchemy-wait-for-outputs (with-current-buffer new-buffer sql-buffer))
      (diff old-data-file new-data-file))))
    
(defun gensqlalchemy-info ()
  "Show info about current specification.
Currently it prints basic information about this object and all dependent
objects."
  (interactive)
  (let ((spec-name (gensqlalchemy-specification))
        (default-directory (gensqlalchemy-specification-directory nil t)))
    (compilation-start (format "%s --names --source --limit='^%s$' %s"
                               gensqlalchemy-gsql spec-name gensqlalchemy-specification-directory))))

(defun gensqlalchemy-sql-function-file ()
  "Visit SQL file associated with current function."
  (interactive)
  (let ((name (with-gensqlachemy-specification
               (unless (re-search-forward "^    name = ['\"]\\(.*\\)['\"]" nil t)
                 (error "Function name not found"))
               (match-string 1))))
    (find-file-other-window (concat "sql/" (match-string 1) ".sql"))))

(defun gensqlalchemy-show-error ()
  "Try to show specification error from the last traceback in current buffer."
  (interactive)
  (let ((regexp "^  File \"\\(.*/dbdefs/.*\\.py\\)\", line \\([0-9]+\\), in .*$"))
    (when (or (re-search-backward regexp nil t)
              (re-search-forward regexp nil t))
      (let ((file (match-string-no-properties 1))
            (line (match-string-no-properties 2))
            (overlay (make-overlay (match-beginning 0) (match-end 0))))
        (overlay-put overlay 'face 'highlight)
        (find-file-other-window file)
        (goto-char 1)
        (forward-line (1- (car (read-from-string line))))))))

;;; Announce

(provide 'gensqlalchemy)

;;; gensqlalchemy.el ends here
