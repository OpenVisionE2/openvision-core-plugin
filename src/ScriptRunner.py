#!/usr/bin/python
# -*- coding: utf-8 -*-
# for localized messages
from . import _, PluginLanguageDomain

from Screens.Screen import Screen
from Screens.Console import Console
from Screens.Setup import Setup
from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.Sources.StaticText import StaticText
from Components.config import config, ConfigSubsection, ConfigYesNo
from IPKInstaller import OpkgInstaller
from Components.PluginComponent import plugins
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from os import path, mkdir, listdir, rename

config.scriptrunner = ConfigSubsection()
config.scriptrunner.close = ConfigYesNo(default=False)
config.scriptrunner.showinextensions = ConfigYesNo(default=False)


def updateExtensions(configElement):
	plugins.clearPluginList()
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))


config.scriptrunner.showinextensions.addNotifier(updateExtensions, initial_call=False)


def ScriptRunnerAutostart(reason, session=None, **kwargs):
	pass


class VISIONScriptRunner(OpkgInstaller):
	def __init__(self, session, list=None):
		if not list:
			list = []
			if path.exists('/usr/scripts') and not path.exists('/usr/script'):
				rename('/usr/scripts', '/usr/script')
			if not path.exists('/usr/script'):
				mkdir('/usr/script', 0o755)
			f = listdir('/usr/script')
			for line in f:
				parts = line.split()
				pkg = parts[0]
				if pkg.find('.sh') >= 0:
					list.append(pkg)
		OpkgInstaller.__init__(self, session, list)
		self.setTitle(_("Vision Script Runner"))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))
		self["key_green"] = StaticText("")
		self["key_blue"] = StaticText("")
		if list:
			self["key_green"].setText(_("Run"))
			self["key_blue"].setText(_("Invert"))
		else:
			self["key_green"].setText("")
			self["key_blue"].setText("")

		self['myactions'] = ActionMap(["ColorActions", "MenuActions"], {
			"menu": self.createSetup,
			"red": self.close,
			}, -1)

	def createSetup(self):
		self.session.open(Setup, "visionscriptrunner", "SystemPlugins/Vision", PluginLanguageDomain)

	def install(self):
		list = self.list.getSelectionsList()
		cmdList = []
		for item in list:
			cmdList.append('chmod +x /usr/script/' + item[0] + ' && . ' + '/usr/script/' + str(item[0]))
		if len(cmdList) < 1 and len(self.list.list):
			cmdList.append('chmod +x /usr/script/' + self.list.getCurrent()[0][0] + ' && . ' + '/usr/script/' + str(self.list.getCurrent()[0][0]))
		if len(cmdList) > 0:
			self.session.open(Console, cmdlist=cmdList, closeOnSuccess=config.scriptrunner.close.value)
