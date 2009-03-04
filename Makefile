# Edit the paths below to suit your needs.
LIB = /usr/local/lib/python%d.%d/site-packages
SHARE = /usr/local/share

lib := $(shell python -c 'import sys; print "$(LIB)".find("%d") != -1 and \
	                 "$(LIB)" % sys.version_info[:2] or "$(LIB)"')

.PHONY: translations

all: check-lib compile translations

compile:
	@echo "Compiling Python libraries from source..."
	@python -c "import compileall; compileall.compile_dir('lib')" >/dev/null

translations:
	make -C translations

install: check-lib $(SHARE)/pytis
	cp -ruv translations $(SHARE)/pytis
	cp -ruv lib/pytis $(lib)

uninstall:
	rm -rf $(SHARE)/pytis
	rm -rf $(lib)/pytis

cvs-install: check-lib compile translations link-lib link-share

check-lib:
	@python -c "import sys; '$(lib)' not in sys.path and sys.exit(1)" || \
           echo 'WARNING: $(lib) not in Python path!'

link-lib:
	@if [ -d $(lib)/pytis ]; then echo "$(lib)/pytis already exists!"; \
	else echo "Linking Pytis libraries to $(lib)/pytis"; \
	ln -s $(CURDIR)/lib/pytis $(lib)/pytis; fi

link-share: link-share-translations

link-share-%: $(SHARE)/pytis
	@if [ -d $(SHARE)/pytis/$* ]; then echo "$(SHARE)/pytis/$* already exists!"; \
	else echo "Linking $* to $(SHARE)/pytis"; ln -s $(CURDIR)/$* $(SHARE)/pytis; fi

cvs-update: do-cvs-update compile translations

do-cvs-update:
	@echo "All local modifications will be lost and owerwritten with clean repository copies!"
	@echo -n "Press Enter to continue or Ctrl-C to abort: "
	@read || exit 1
	cvs update -dPC

$(SHARE)/pytis:
	mkdir $(SHARE)/pytis

tags:
	./tools/make-tags.sh

version = $(shell echo 'import pytis; print pytis.__version__' | python)
dir = pytis-$(version)
file = pytis-$(version).tar.gz

release: compile translations
	@ln -s .. releases/$(dir)
	@if [ -e releases/$(file) ]; then \
	   echo "Removing old file $(file)"; rm releases/$(file); fi
	@echo "Generating $(file)..."
	@(cd releases; tar --exclude "CVS" --exclude "*~" --exclude "#*" \
	     --exclude ".#*" --exclude "*.pyo" \
	     --exclude demo --exclude releases --exclude extensions \
	     -czhf $(file) $(dir))
	@rm releases/$(dir)