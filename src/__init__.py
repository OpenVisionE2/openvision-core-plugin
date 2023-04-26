# -*- coding: utf-8 -*-
from gettext import bindtextdomain, dgettext, gettext
from Components.Language import language
from Tools.Directories import resolveFilename, SCOPE_PLUGINS


PluginLanguageDomain = "vision"
PluginLanguagePath = "SystemPlugins/Vision/locale"


def pluginlanguagedomain():
	return PluginLanguageDomain


def localeInit():
	bindtextdomain(PluginLanguageDomain, resolveFilename(SCOPE_PLUGINS, PluginLanguagePath))


def _(txt):
	if dgettext(PluginLanguageDomain, txt):
		return dgettext(PluginLanguageDomain, txt)
	else:
		print("[" + PluginLanguageDomain + "] Fallback to default translation for " + txt)
		return gettext(txt)


localeInit()
language.addCallback(localeInit)
