dist_noinst_SCRIPTS = xml2po.py

plugindir = $(libdir)/enigma2/python/Plugins/SystemPlugins/Vision

LANGS = ar bg ca cs da de el en es et fa fi fr fy he hr hu id is it ku lt lv nb nl nn pl pt pt_BR ro ru sk sl sr sv th tr uk vi zh_CN zh_HK sl sr th tr uk zh_CN
LANGMO = $(LANGS:=.mo)
LANGPO = $(LANGS:=.po)

EXTRA_DIST = $(LANGPO)

# the TRANSLATORS: allows putting translation comments before the to-be-translated line.
vision-py.pot: $(top_srcdir)/src/*.py
	$(XGETTEXT) --no-wrap -L Python --from-code=UTF-8 --add-comments="TRANSLATORS:" -d @PACKAGE_NAME@ -s -o $@ $^

vision-xml.pot: $(srcdir)/xml2po.py $(top_srcdir)/src/*.xml
	$(PYTHON) $^ > $@

vision.pot: vision-py.pot vision-xml.pot
	sed --in-place vision-py.pot --expression=s/CHARSET/UTF-8/
	sed --in-place vision-xml.pot --expression=s/CHARSET/UTF-8/
	cat $^ | $(MSGUNIQ) --no-wrap --no-location -o $@ -

%.po: vision.pot
	if [ -f $@ ]; then \
		$(MSGMERGE) --backup=none --no-wrap --no-location -s -N -U $@ $< && touch $@; \
	else \
		$(MSGINIT) -l $@ -o $@ -i $< --no-translator; \
	fi

.po.mo:
	$(MSGFMT) -o $@ $<

BUILT_SOURCES = $(LANGMO)
CLEANFILES = $(LANGMO) vision-py.pot vision.pot

dist-hook: $(LANGPO)

install-data-local: $(LANGMO)
	for lang in $(LANGS); do \
		$(mkinstalldirs) $(DESTDIR)$(plugindir)/locale/$$lang/LC_MESSAGES; \
		$(INSTALL_DATA) $$lang.po $(DESTDIR)$(plugindir)/locale/vision-$$lang.po; \
		$(INSTALL_DATA) $$lang.mo $(DESTDIR)$(plugindir)/locale/$$lang/LC_MESSAGES/vision.mo; \
	done

uninstall-local:
	for lang in $(LANGS); do \
		$(RM) $(DESTDIR)$(plugindir)/locale/vision-$$lang.po; \
		$(RM) $(DESTDIR)$(plugindir)/locale/$$lang/LC_MESSAGES/vision.mo; \
	done
