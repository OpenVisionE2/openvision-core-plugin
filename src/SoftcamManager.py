# -*- coding: utf-8 -*-
from six import PY2, ensure_str

import re
from os import path, makedirs, remove, rename, symlink, mkdir, listdir, unlink
from datetime import datetime
from time import time, sleep

from enigma import eTimer, eConsoleAppContainer

from . import _, PluginLanguageDomain
import Components.Task
from Components.ActionMap import ActionMap
from Components.Sources.StaticText import StaticText
from Components.Label import Label
from Components.Button import Button
from Components.ScrollLabel import ScrollLabel
from Components.Pixmap import MultiPixmap
from Components.config import config, configfile, ConfigLocations, ConfigNumber, ConfigSubsection, ConfigYesNo, getConfigListEntry, ConfigSelection
from Components.Console import Console
from Components.FileList import MultiFileSelectList
from Components.PluginComponent import plugins
from Tools.camcontrol import CamControl
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Components.SystemInfo import BoxInfo
from Components.ConfigList import ConfigListScreen

config.softcammanager = ConfigSubsection()
config.softcammanager.softcams_autostart = ConfigLocations(default='')
config.softcammanager.softcamtimerenabled = ConfigYesNo(default=True)
config.softcammanager.softcamtimer = ConfigNumber(default=6)
config.softcammanager.showinextensions = ConfigYesNo(default=True)
config.misc.softcams = ConfigSelection(default="None", choices=CamControl("softcam").getList())

softcamautopoller = None


def updateExtensions(configElement):
	plugins.clearPluginList()
	plugins.readPluginList(resolveFilename(SCOPE_PLUGINS))


config.softcammanager.showinextensions.addNotifier(updateExtensions, initial_call=False)


def SoftcamAutostart(reason, session=None, **kwargs):
	"""called with reason=1 to during shutdown, with reason=0 at startup?"""
	global softcamautopoller
	if reason == 0:
		if PY2:
			print("[SoftcamManager] AutoStart Enabled")
			if path.exists("/tmp/SoftcamsDisableCheck"):
				remove("/tmp/SoftcamsDisableCheck")
			softcamautopoller = SoftcamAutoPoller()
			softcamautopoller.start()
		else:
			link = "/etc/init.d/softcam"
			print("[SoftcamAutostart] config.misc.softcams.value=%s" % (config.misc.softcams.value))
			if path.exists(link) and config.misc.softcams.value != "None":
				scr = "softcam.%s" % config.misc.softcams.value
				unlink(link)
				symlink(scr, link)
				cmd = "%s %s" % (link, "start")
				print("[SoftcamAutostart][command]Executing %s" % cmd)
				eConsoleAppContainer().execute(cmd)
			else:
				print("[SoftcamManager] AutoStart Enabled")
				if path.exists("/tmp/SoftcamsDisableCheck"):
					remove("/tmp/SoftcamsDisableCheck")
				softcamautopoller = SoftcamAutoPoller()
				softcamautopoller.start()
	elif reason == 1:
		# Stop Poller
		if softcamautopoller is not None:
			softcamautopoller.stop()
			softcamautopoller = None


class VISIONSoftcamManager(Screen):
	skin = """
	<screen name="VISIONSoftcamManager" position="center,center" size="560,400">
		<ePixmap pixmap="buttons/red.png" position="0,0" size="140,40" alphatest="blend"/>
		<ePixmap pixmap="buttons/green.png" position="140,0" size="140,40" alphatest="blend"/>
		<ePixmap pixmap="buttons/yellow.png" position="280,0" size="140,40" alphatest="blend"/>
		<ePixmap pixmap="buttons/blue.png" position="420,0" size="140,40" alphatest="blend"/>
		<widget name="key_red" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1"/>
		<widget name="key_green" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1"/>
		<widget name="key_yellow" position="280,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="1"/>
		<widget name="key_blue" position="420,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#a08500" transparent="1"/>
		<widget name="lab7" position="40,60" size="170,20" font="Regular; 22" halign="right" zPosition="2" transparent="0"/>
		<widget name="list" position="225,60" size="240,100" transparent="0" scrollbarMode="showOnDemand"/>
		<widget name="lab8" position="40,165" size="170,30" font="Regular; 22" halign="right" zPosition="2" transparent="0"/>
		<widget name="activecam" position="225,166" size="240,100" font="Regular; 20" halign="left" zPosition="2" transparent="0" noWrap="1"/>
		<applet type="onLayoutFinish">
			self["list"].instance.setItemHeight(25)
		</applet>
	</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Vision Softcam"))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))

		self['lab7'] = Label(_('Select:'))
		self['lab8'] = Label(_('Active:'))
		self['activecam'] = Label()
		self.onChangedEntry = []

		self.sentsingle = ""
		self.selectedFiles = config.softcammanager.softcams_autostart.value
		self.defaultDir = '/usr/softcams/'
		self.emlist = MultiFileSelectList(self.selectedFiles, self.defaultDir, showDirectories=False)
		self["list"] = self.emlist

		self['myactions'] = ActionMap(['ColorActions', 'OkCancelActions', "TimerEditActions", "MenuActions"], {
			'ok': self.keyStart,
			'cancel': self.close,
			'red': self.close,
			'green': self.keyStart,
			'yellow': self.getRestartPID,
			'blue': self.changeSelectionState,
			'log': self.showLog,
			'menu': self.createSetup,
		}, -1)

		self["key_red"] = Button(_("Close"))
		self["key_green"] = StaticText("")
		self["key_yellow"] = StaticText("")
		self["key_blue"] = StaticText("")

		self["key_menu"] = StaticText(_("MENU"))
		self["key_info"] = StaticText(_("INFO"))

		self.currentactivecam = ""
		self.activityTimer = eTimer()
		self.activityTimer.timeout.get().append(self.getActivecam)
		self.Console = Console()
		self.showActivecam()
		if not self.selectionChanged in self["list"].onSelectionChanged:
			self["list"].onSelectionChanged.append(self.selectionChanged)

	def createSummary(self):
		from Screens.PluginBrowser import PluginBrowserSummary
		return PluginBrowserSummary

	def selectionChanged(self):
		cams = []
		cams = listdir('/usr/softcams')
		selcam = ''
		if path.islink('/usr/softcams/oscam'):
			current = self["list"].getCurrent()[0]
			selcam = current[0]
			print('[SoftcamManager] Selected cam: ' + str(selcam))
			if self.currentactivecam.find(selcam) < 0:
				self["key_green"].setText(_("Start"))
				self["key_yellow"].setText("")
			else:
				self["key_green"].setText(_("Stop"))
				self["key_yellow"].setText(_("Restart"))

			if current[2] is True:
				self["key_blue"].setText(_("Disable startup"))
			else:
				self["key_blue"].setText(_("Enable startup"))
			self.saveSelection()
		desc = _('Active:') + ' ' + self['activecam'].text
		for cb in self.onChangedEntry:
			cb(selcam, desc)

	def changeSelectionState(self):
		cams = []
		if path.exists('/usr/softcams/'):
			cams = listdir('/usr/softcams')
		if cams:
			self["list"].changeSelectionState()
			self.selectedFiles = self["list"].getSelectedList()

	def saveSelection(self):
		self.selectedFiles = self["list"].getSelectedList()
		config.softcammanager.softcams_autostart.value = self.selectedFiles
		config.softcammanager.softcams_autostart.save()
		configfile.save()

	def showActivecam(self):
		scanning = _("Wait please while scanning\nfor softcam's...")
		self['activecam'].setText(scanning)
		self.activityTimer.start(10)

	def getActivecam(self):
		self.activityTimer.stop()
		active = []
		for x in self["list"].list:
			active.append(x[0][0])
		activelist = ",".join(active)
		if activelist:
			self.Console.ePopen("ps.procps -C " + activelist + " | grep -v 'CMD' | sed 's/</ /g' | awk '{print $4}' | awk '{a[$1] = $0} END { for (x in a) { print a[x] } }'", self.showActivecam2)
		else:
			self['activecam'].setText('')
			self['activecam'].show()
		# self.Console.ePopen("ps.procps | grep softcams | grep -v 'grep' | sed 's/</ /g' | awk '{print $5}' | awk '{a[$1] = $0} END { for (x in a) { print a[x] } }' | awk -F'[/]' '{print $4}'", self.showActivecam2)

	def showActivecam2(self, result, retval, extra_args):
		result = ensure_str(result)
		if retval == 0:
			self.currentactivecamtemp = result
			self.currentactivecam = "".join([s for s in self.currentactivecamtemp.splitlines(True) if s.strip("\r\n")])
			self.currentactivecam = self.currentactivecam.replace("\n", ", ")
			if path.exists("/tmp/SoftcamsScriptsRunning"):
				file = open("/tmp/SoftcamsScriptsRunning")
				SoftcamsScriptsRunning = file.read()
				file.close()
				SoftcamsScriptsRunning = SoftcamsScriptsRunning.replace("\n", ", ")
				self.currentactivecam += SoftcamsScriptsRunning
			print("[SoftcamManager] Active:%s SoftcamSetup:%s" % (self.currentactivecam, config.misc.softcams.value))
			if config.misc.softcams.value != "None":
				self["activecam"].setText(_("Softcam Setup [%s]") % config.misc.softcams.value)
			else:
				self["activecam"].setText(self.currentactivecam)
			self["activecam"].show()
		else:
			print("[SoftcamManager] Result failed: " + str(result))
		self.selectionChanged()

	def keyStart(self):
		cams = []
		if path.exists('/usr/softcams/'):
			cams = listdir('/usr/softcams')
		if cams:
			self.sel = self['list'].getCurrent()[0]
			selcam = self.sel[0]
			if self.currentactivecam.find(selcam) < 0:
				if selcam.lower().endswith('oscam'):
					if not path.exists('/etc/tuxbox/config/oscam/oscam.conf'):
						self.session.open(MessageBox, _("No config files found, please setup Oscam first\nin /etc/tuxbox/config/oscam"), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
					else:
						self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
				elif selcam.lower().endswith('smod'):
					if not path.exists('/etc/tuxbox/config/oscam-smod/oscam.conf'):
						self.session.open(MessageBox, _("No config files found, please setup Oscam-smod first\nin /etc/tuxbox/config/oscam-smod"), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
					else:
						self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
				elif selcam.lower().endswith('emu'):
					if not path.exists('/etc/tuxbox/config/oscam-emu/oscam.conf'):
						self.session.open(MessageBox, _("No config files found, please setup Oscam-emu first\nin /etc/tuxbox/config/oscam-emu"), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
					else:
						self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
				elif selcam.lower().startswith('ncam'):
					if not path.exists('/etc/tuxbox/config/ncam/ncam.conf'):
						self.session.open(MessageBox, _("No config files found, please setup Ncam first\nin /etc/tuxbox/config/ncam"), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
					else:
						self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
				else:
					self.session.open(MessageBox, _("Found non-standard softcam, trying to start, this may fail."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
					self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
			else:
				self.session.openWithCallback(self.showActivecam, VISIONStopCam, self.sel[0])

	def getRestartPID(self):
		cams = []
		if path.exists('/usr/softcams/'):
			cams = listdir('/usr/softcams')
		if cams:
			self.sel = self['list'].getCurrent()[0]
			selectedcam = self.sel[0]
			self.Console.ePopen("pidof " + selectedcam, self.keyRestart, selectedcam)

	def keyRestart(self, result, retval, extra_args):
		result = ensure_str(result)
		selectedcam = extra_args
		strpos = self.currentactivecam.find(selectedcam)
		if strpos < 0:
			return
		else:
			if retval == 0:
				stopcam = result
				print('[SoftcamManager] Stopping ' + selectedcam + ' PID ' + stopcam.replace("\n", ""))
				now = datetime.now()
				open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Stopping: " + selectedcam + "\n")
				self.Console.ePopen("kill -9 " + stopcam.replace("\n", ""))
				sleep(4)
			else:
				print('[SoftcamManager] Result failed: ' + str(result))
			if selectedcam.lower().endswith('oscam') and path.exists('/etc/tuxbox/config/oscam/oscam.conf') == True:
				self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
			if selectedcam.lower().startswith('ncam') and path.exists('/etc/tuxbox/config/ncam/ncam.conf') == True:
				self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
			if selectedcam.lower().endswith('smod') and path.exists('/etc/tuxbox/config/oscam-smod/oscam.conf') == True:
				self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
			if selectedcam.lower().endswith('emu') and path.exists('/etc/tuxbox/config/oscam-emu/oscam.conf') == True:
				self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])
			if selectedcam.lower().endswith('oscam') and path.exists('/etc/tuxbox/config/oscam/oscam.conf') == False:
				if not path.exists('/etc/tuxbox/config/oscam'):
					makedirs('/etc/tuxbox/config/oscam')
				self.session.open(MessageBox, _("No config files found, please setup Oscam first\nin /etc/tuxbox/config/oscam."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
			if selectedcam.lower().startswith('ncam') and path.exists('/etc/tuxbox/config/ncam/ncam.conf') == False:
				if not path.exists('/etc/tuxbox/config/ncam'):
					makedirs('/etc/tuxbox/config/ncam')
				self.session.open(MessageBox, _("No config files found, please setup Ncam first\nin /etc/tuxbox/config/ncam."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
			if selectedcam.lower().endswith('emu') and path.exists('/etc/tuxbox/config/oscam-emu/oscam.conf') == False:
				if not path.exists('/etc/tuxbox/config/oscam-emu'):
					makedirs('/etc/tuxbox/config/oscam-emu')
				self.session.open(MessageBox, _("No config files found, please setup Oscam-emu first\nin /etc/tuxbox/config/oscam-emu."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
			if selectedcam.lower().endswith('smod') and path.exists('/etc/tuxbox/config/oscam-smod/oscam.conf') == False:
				if not path.exists('/etc/tuxbox/config/oscam-smod'):
					makedirs('/etc/tuxbox/config/oscam-smod')
				self.session.open(MessageBox, _("No config files found, please setup Oscam-smod first\nin /etc/tuxbox/config/oscam-smod."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
			if not (selectedcam.lower().endswith('oscam') or not selectedcam.lower().startswith('ncam') or not selectedcam.lower().endswith('emu') or not selectedcam.lower().endswith('smod')):
				self.session.open(MessageBox, _("Found non-standard softcam, trying to start, this may fail."), MessageBox.TYPE_INFO, timeout=10, close_on_any_key=True)
				self.session.openWithCallback(self.showActivecam, VISIONStartCam, self.sel[0])

	def showLog(self):
		self.session.open(VISIONSoftcamLog)

	def createSetup(self):
		self.session.open(VISIONSoftcamMenu)

	def myclose(self):
		self.close()


class VISIONSoftcamMenu(ConfigListScreen, Screen):
	skin = """
		<screen name="VISIONSoftcamMenu" position="center,center" size="500,285" title="Softcam Menu">
			<ePixmap pixmap="buttons/red.png" position="0,0" size="140,40" alphatest="blend" />
			<ePixmap pixmap="buttons/green.png" position="140,0" size="140,40" alphatest="blend" />
			<widget name="key_red" position="0,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#9f1313" transparent="1" />
			<widget name="key_green" position="140,0" zPosition="1" size="140,40" font="Regular;20" halign="center" valign="center" backgroundColor="#1f771f" transparent="1" />
			<widget name="config" position="10,45" size="480,250" scrollbarMode="showOnDemand" />
		</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, [])
		self.skinName = "VISIONSoftcamMenu"
		Screen.setTitle(self, _("Vision Softcam setup"))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))

		self.onChangedEntry = []
		self.list = []
		ConfigListScreen.__init__(self, self.list, session=self.session, on_change=self.changedEntry)
		self.createSetup()

		self["actions"] = ActionMap(["SetupActions", "MenuActions"], {
			"cancel": self.keyCancel,
			"save": self.keySave,
			"menu": self.closeRecursive,
		}, -2)
		self["key_red"] = Button(_("Cancel"))
		self["key_green"] = Button(_("Save"))

	def createSetup(self):
		self.editListEntry = None
		self.list = []
		self.list.append(getConfigListEntry(_("Enable frozen check"), config.softcammanager.softcamtimerenabled))
		if config.softcammanager.softcamtimerenabled.value:
			self.list.append(getConfigListEntry(_("Check interval on minutes"), config.softcammanager.softcamtimer))
		self["config"].list = self.list
		self["config"].setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.createSetup()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.createSetup()

	def changedEntry(self):
		for x in self.onChangedEntry:
			x()

	def getCurrentEntry(self):
		return self["config"].getCurrent()[0]

	def getCurrentValue(self):
		return str(self["config"].getCurrent()[1].getText())

	def keySave(self):
		for x in self["config"].list:
			x[1].save()
		if config.softcammanager.softcamtimerenabled.value:
			print("[SoftcamManager] Timer check enabled")
			softcamautopoller.start()
		else:
			print("[SoftcamManager] Timer check disabled")
			softcamautopoller.stop()
		self.close()

	def keyCancel(self):
		for x in self["config"].list:
			x[1].cancel()
		self.close()


class VISIONStartCam(Screen):
	skin = """
	<screen name="VISIONStartCam" position="center,center" size="484, 150" title="Starting Softcam">
		<widget name="connect" position="217, 0" size="64,64" zPosition="2" pixmaps="Vision_HD_Common/busy/busy1.png,Vision_HD_Common/busy/busy2.png,Vision_HD_Common/busy/busy3.png,Vision_HD_Common/busy/busy4.png,Vision_HD_Common/busy/busy5.png,Vision_HD_Common/busy/busy6.png,Vision_HD_Common/busy/busy7.png,Vision_HD_Common/busy/busy8.png,Vision_HD_Common/busy/busy9.png,Vision_HD_Common/busy/busy9.png,Vision_HD_Common/busy/busy10.png,Vision_HD_Common/busy/busy11.png,Vision_HD_Common/busy/busy12.png,Vision_HD_Common/busy/busy13.png,Vision_HD_Common/busy/busy14.png,Vision_HD_Common/busy/busy15.png,Vision_HD_Common/busy/busy17.png,Vision_HD_Common/busy/busy18.png,Vision_HD_Common/busy/busy19.png,Vision_HD_Common/busy/busy20.png,Vision_HD_Common/busy/busy21.png,Vision_HD_Common/busy/busy22.png,Vision_HD_Common/busy/busy23.png,Vision_HD_Common/busy/busy24.png"  transparent="1" alphatest="blend"/>
		<widget name="lab7" position="10, 80" halign="center" size="460, 60" zPosition="1" font="Regular;20" valign="top" transparent="1"/>
	</screen>"""

	def __init__(self, session, selectedcam):
		Screen.__init__(self, session)
		Screen.setTitle(self, _("Softcam starting..."))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))
		self['connect'] = MultiPixmap()
		self['lab7'] = Label(_("Please wait while starting\n") + selectedcam + '...')
		global startselectedcam
		startselectedcam = selectedcam
		self.Console = Console()
		self.activityTimer = eTimer()
		self.activityTimer.timeout.get().append(self.updatepix)
		self.onShow.append(self.startShow)
		self.onClose.append(self.delTimer)

	def startShow(self):
		self.count = 0
		self['connect'].setPixmapNum(0)
		if startselectedcam.endswith('.sh'):
			if path.exists('/tmp/SoftcamsScriptsRunning'):
				data = open('/tmp/SoftcamsScriptsRunning').read()
				if data.find(startselectedcam) >= 0:
					filewrite = open('/tmp/SoftcamsScriptsRunning.tmp', 'w')
					fileread = open('/tmp/SoftcamsScriptsRunning')
					filewrite.writelines([l for l in fileread.readlines() if startselectedcam not in l])
					rename('/tmp/SoftcamsScriptsRunning.tmp', '/tmp/SoftcamsScriptsRunning')
				elif data.find(startselectedcam) < 0:
					open('/tmp/SoftcamsScriptsRunning', 'a').write(startselectedcam + '\n')
			else:
				open('/tmp/SoftcamsScriptsRunning', 'w').write(startselectedcam + '\n')
			print('[SoftcamManager] Starting ' + startselectedcam)
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Starting " + startselectedcam + "\n")
			self.Console.ePopen('/usr/softcams/' + startselectedcam + ' start')
		else:
			if path.exists('/tmp/SoftcamsDisableCheck'):
				data = open('/tmp/SoftcamsDisableCheck').read()
				if data.find(startselectedcam) >= 0:
					now = datetime.now()
					open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Initialised timed check for " + stopselectedcam + "\n")
					fileread = open('/tmp/SoftcamsDisableCheck')
					filewrite = open('/tmp/SoftcamsDisableCheck.tmp', 'w')
					filewrite.writelines([l for l in fileread.readlines() if startselectedcam not in l])
					rename('/tmp/SoftcamsDisableCheck.tmp', '/tmp/SoftcamsDisableCheck')
			print('[SoftcamManager] Starting ' + startselectedcam)
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Starting " + startselectedcam + "\n")
			if startselectedcam.lower().startswith('oscam') or startselectedcam.lower().startswith('ncam'):
				self.Console.ePopen('ulimit -s 1024;/usr/softcams/' + startselectedcam + ' -b')
			else:
				self.Console.ePopen('ulimit -s 1024;/usr/softcams/' + startselectedcam)
		self.activityTimer.start(1)

	def updatepix(self):
		self.activityTimer.stop()
		maxcount = 25
		if self.count < maxcount:  # timer on screen
			self["connect"].setPixmapNum(self.count % 24)
			self.activityTimer.start(120)  # cycle speed
			self.count += 1
		else:
			self.hide()
			self.close()

	def delTimer(self):
		del self.activityTimer


class VISIONStopCam(Screen):
	skin = """
	<screen name="VISIONStopCam" position="center,center" size="484, 150">
		<widget name="connect" position="217, 0" size="64,64" zPosition="2" pixmaps="Vision_HD_Common/busy/busy1.png,Vision_HD_Common/busy/busy2.png,Vision_HD_Common/busy/busy3.png,Vision_HD_Common/busy/busy4.png,Vision_HD_Common/busy/busy5.png,Vision_HD_Common/busy/busy6.png,Vision_HD_Common/busy/busy7.png,Vision_HD_Common/busy/busy8.png,Vision_HD_Common/busy/busy9.png,Vision_HD_Common/busy/busy9.png,Vision_HD_Common/busy/busy10.png,Vision_HD_Common/busy/busy11.png,Vision_HD_Common/busy/busy12.png,Vision_HD_Common/busy/busy13.png,Vision_HD_Common/busy/busy14.png,Vision_HD_Common/busy/busy15.png,Vision_HD_Common/busy/busy17.png,Vision_HD_Common/busy/busy18.png,Vision_HD_Common/busy/busy19.png,Vision_HD_Common/busy/busy20.png,Vision_HD_Common/busy/busy21.png,Vision_HD_Common/busy/busy22.png,Vision_HD_Common/busy/busy23.png,Vision_HD_Common/busy/busy24.png"  transparent="1" alphatest="blend"/>
		<widget name="lab7" position="10, 80" halign="center" size="460, 60" zPosition="1" font="Regular;20" valign="top" transparent="1"/>
	</screen>"""

	def __init__(self, session, selectedcam):
		Screen.__init__(self, session)
		global stopselectedcam
		stopselectedcam = selectedcam
		Screen.setTitle(self, _("Softcam stopping..."))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))
		self['connect'] = MultiPixmap()
		self['lab7'] = Label(_("Please wait while stopping\n") + selectedcam + '...')
		self.Console = Console()
		self.activityTimer = eTimer()
		self.activityTimer.timeout.get().append(self.updatepix)
		self.onShow.append(self.getStopPID)
		self.onClose.append(self.delTimer)

	def getStopPID(self):
		if stopselectedcam.endswith('.sh'):
			self.curpix = 0
			self.count = 0
			self['connect'].setPixmapNum(0)
			print('[SoftcamManager] Stopping ' + stopselectedcam)
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Stopping " + stopselectedcam + "\n")
			self.Console.ePopen('/usr/softcams/' + stopselectedcam + ' stop')
			if path.exists('/tmp/SoftcamsScriptsRunning'):
				remove('/tmp/SoftcamsScriptsRunning')
			if path.exists('/etc/SoftcamsAutostart'):
				data = open('/etc/SoftcamsAutostart').read()
				finddata = data.find(stopselectedcam)
				if data.find(stopselectedcam) >= 0:
					print('[SoftcamManager] Temporarily disabled timed check for ' + stopselectedcam)
					now = datetime.now()
					open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Temporarily disabled timed check for " + stopselectedcam + "\n")
					open('/tmp/SoftcamsDisableCheck', 'a').write(stopselectedcam + '\n')
			self.activityTimer.start(1)
		else:
			self.Console.ePopen("pidof " + stopselectedcam, self.startShow)

	def startShow(self, result, retval, extra_args):
		result = ensure_str(result)
		if retval == 0:
			self.count = 0
			self['connect'].setPixmapNum(0)
			stopcam = result
			print("[SoftcamManager][startShow] stopcam=%s" % stopcam)
			if path.exists('/etc/SoftcamsAutostart'):
				data = open('/etc/SoftcamsAutostart').read()
				finddata = data.find(stopselectedcam)
				if data.find(stopselectedcam) >= 0:
					print('[SoftcamManager] Temporarily disabled timed check for ' + stopselectedcam)
					now = datetime.now()
					open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Temporarily disabled timed check for " + stopselectedcam + "\n")
					open('/tmp/SoftcamsDisableCheck', 'a').write(stopselectedcam + '\n')
			print('[SoftcamManager] Stopping ' + stopselectedcam + ' PID ' + stopcam.replace("\n", ""))
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Stopping " + stopselectedcam + "\n")
			self.Console.ePopen("kill -9 " + stopcam.replace("\n", ""))
			self.activityTimer.start(1)

	def updatepix(self):
		self.activityTimer.stop()
		if self.count < 25:  # timer on screen
			self["connect"].setPixmapNum(self.count % 24)
			self.activityTimer.start(120)  # cycle speed
			self.count += 1
		else:
			self.hide()
			self.close()

	def delTimer(self):
		del self.activityTimer


class VISIONSoftcamLog(Screen):
	skin = """
<screen name="VISIONSoftcamLog" position="center,center" size="560,400">
	<widget name="list" position="0,0" size="560,400" font="Regular;14"/>
</screen>"""

	def __init__(self, session):
		self.session = session
		Screen.__init__(self, session)
		self.setTitle(_("Vision Softcam logs"))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))

		if path.exists('/var/volatile/tmp/cam.check.log'):
			softcamlog = open('/var/volatile/tmp/cam.check.log').read()
		else:
			softcamlog = ""
		self["list"] = ScrollLabel(str(softcamlog))
		self["setupActions"] = ActionMap(["SetupActions", "ColorActions", "DirectionActions"], {
			"cancel": self.cancel,
			"ok": self.cancel,
			"up": self["list"].pageUp,
			"down": self["list"].pageDown
		 }, -2)

	def cancel(self):
		self.close()


class SoftcamAutoPoller:
	"""Automatically Poll SoftCam"""

	def __init__(self):
		# Init Timer
		if not path.exists('/usr/softcams'):
			mkdir('/usr/softcams', 0o755)
		if not path.exists('/etc/scce'):
			mkdir('/etc/scce', 0o755)
		if not path.exists('/etc/tuxbox/config'):
			mkdir('/etc/tuxbox/config', 0o755)
		if not path.islink('/var/tuxbox'):
			symlink('/etc/tuxbox', '/var/tuxbox')
		if not path.exists('/usr/keys'):
			mkdir('/usr/keys', 0o755)
		if not path.islink('/var/keys'):
			symlink('/usr/keys', '/var/keys')
		if not path.islink('/etc/keys'):
			symlink('/usr/keys', '/etc/keys')
		if not path.islink('/var/scce'):
			symlink('/etc/scce', '/var/scce')
		self.timer = eTimer()

	def start(self):
		if self.softcam_check not in self.timer.callback:
			self.timer.callback.append(self.softcam_check)
		self.timer.startLongTimer(1)

	def stop(self):
		if self.softcam_check in self.timer.callback:
			self.timer.callback.remove(self.softcam_check)
		self.timer.stop()

	def softcam_check(self):
		now = int(time())
		if path.exists('/tmp/SoftcamRuningCheck.tmp'):
			remove('/tmp/SoftcamRuningCheck.tmp')

		if config.softcammanager.softcams_autostart:
			Components.Task.job_manager.AddJob(self.createCheckJob())

		if config.softcammanager.softcamtimerenabled.value and path.exists('/tmp/cam.check.log'):
			# 			print("[SoftcamManager] Timer check enabled")
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Timer Check Enabled\n")
			self.timer.startLongTimer(config.softcammanager.softcamtimer.value * 60)
		else:
			now = datetime.now()
			open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Timer Check Disabled\n")
			# 			print("[SoftcamManager] Timer check disabled")
			softcamautopoller.stop()

	def createCheckJob(self):
		job = Components.Task.Job(_("SoftcamCheck"))

		task = Components.Task.PythonTask(job, _("Checking softcams..."))
		task.work = self.JobStart
		task.weighting = 1

		return job

	def JobStart(self):
		self.autostartcams = config.softcammanager.softcams_autostart.value
		self.Console = Console()
		if BoxInfo.getItem("OScamInstalled") and not path.exists("/usr/softcams/oscam"):
			self.Console.ePopen('ln -s /usr/bin/*oscam* /usr/softcams/')
		if BoxInfo.getItem("NCamInstalled") and not path.exists("/usr/softcams/ncam"):
		    self.Console.ePopen('ln -s /usr/bin/ncam /usr/softcams/')
		if path.exists('/tmp/cam.check.log'):
			if path.getsize('/tmp/cam.check.log') > 40000:
				fh = open('/tmp/cam.check.log', 'rb+')
				fh.seek(-40000, 2)
				data = fh.read()
				fh.seek(0)  # rewind
				fh.write(data)
				fh.truncate()
				fh.close()

		for softcamcheck in self.autostartcams:
			softcamcheck = softcamcheck.replace("/usr/softcams/", "")
			softcamcheck = softcamcheck.replace("\n", "")
			if softcamcheck.endswith('.sh'):
				if path.exists('/tmp/SoftcamsDisableCheck'):
					data = open('/tmp/SoftcamsDisableCheck').read()
				else:
					data = ''
				if data.find(softcamcheck) < 0:
					if path.exists('/tmp/SoftcamsScriptsRunning'):
						data = open('/tmp/SoftcamsScriptsRunning').read()
						if data.find(softcamcheck) < 0:
							open('/tmp/SoftcamsScriptsRunning', 'a').write(softcamcheck + '\n')
							print('[SoftcamManager] Starting ' + softcamcheck)
							self.Console.ePopen('/usr/softcams/' + softcamcheck + ' start')
					else:
						open('/tmp/SoftcamsScriptsRunning', 'w').write(softcamcheck + '\n')
						print('[SoftcamManager] Starting ' + softcamcheck)
						self.Console.ePopen('/usr/softcams/' + softcamcheck + ' start')
			else:
				if path.exists('/tmp/SoftcamsDisableCheck'):
					data = open('/tmp/SoftcamsDisableCheck').read()
				else:
					data = ''
				if data.find(softcamcheck) < 0:
					import process

					p = process.ProcessList()
					softcamcheck_process = str(p.named(softcamcheck)).strip('[]')
					if softcamcheck_process != "":
						if path.exists('/tmp/frozen'):
							remove('/tmp/frozen')
						if path.exists('/tmp/status.html'):
							remove('/tmp/status.html')
						if path.exists('/tmp/index.html'):
							remove('/tmp/index.html')
						print('[SoftcamManager] ' + softcamcheck + ' already running')
						now = datetime.now()
						open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": " + softcamcheck + " running OK\n")
						if softcamcheck.lower().startswith('oscam') or softcamcheck.lower().startswith('ncam'):
							if path.exists('/tmp/status.html'):
								remove('/tmp/status.html')
							port = ''
							if path.exists('/etc/tuxbox/config/oscam/oscam.conf'):
								camconf = '/etc/tuxbox/config/oscam/oscam.conf'
							elif path.exists('/etc/tuxbox/config/ncam/ncam.conf'):
								camconf = '/etc/tuxbox/config/ncam/ncam.conf'
							elif path.exists('/etc/tuxbox/config/oscam-emu/oscam.conf'):
								camconf = '/etc/tuxbox/config/oscam-emu/oscam.conf'
							elif path.exists('/etc/tuxbox/config/oscam-smod/oscam.conf'):
								camconf = '/etc/tuxbox/config/oscam-smod/oscam.conf'
							f = open(camconf, 'r')
							for line in f.readlines():
								if line.find('httpport') != -1:
									port = re.sub("\D", "", line)
							f.close()
							print('[SoftcamManager] Checking if ' + softcamcheck + ' is frozen')
							if port == "":
								port = "16000"
							self.Console.ePopen("wget -T 1 http://127.0.0.1:" + port + "/status.html -O /tmp/status.html &> /tmp/frozen")
							sleep(2)
							frozen = open('/tmp/frozen').read()
							if frozen.find('Unauthorized') != -1 or frozen.find('Authorization Required') != -1 or frozen.find('Forbidden') != -1 or frozen.find('Connection refused') != -1 or frozen.find('100%') != -1 or path.exists('/tmp/status.html'):
								print('[SoftcamManager] ' + softcamcheck + ' is responding like it should')
								now = datetime.now()
								open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": " + softcamcheck + " is responding like it should\n")
							else:
								print('[SoftcamManager] ' + softcamcheck + ' is frozen, restarting...')
								now = datetime.now()
								open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": " + softcamcheck + " is frozen, Restarting...\n")
								print('[SoftcamManager] Stopping ' + softcamcheck)
								now = datetime.now()
								open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": AutoStopping: " + softcamcheck + "\n")
								self.Console.ePopen("killall -9 " + softcamcheck)
								sleep(1)
								print('[SoftcamManager] Starting ' + softcamcheck)
								now = datetime.now()
								open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": AutoStarting: " + softcamcheck + "\n")
								self.Console.ePopen('ulimit -s 1024;/usr/softcams/' + softcamcheck + ' -b')
								sleep(10)

					elif softcamcheck_process == "":
						print("[SoftcamManager] Couldn't find " + softcamcheck + " running, starting " + softcamcheck)
						now = datetime.now()
						open('/tmp/cam.check.log', 'a').write(now.strftime("%Y-%m-%d %H:%M") + ": Couldn't find " + softcamcheck + " running, Starting " + softcamcheck + "\n")
						if softcamcheck.lower().startswith('oscam') or softcamcheck.lower().startswith('ncam'):
							self.Console.ePopen("ps.procps | grep softcams | grep -v grep | awk 'NR==1' | awk '{print $5}'| awk  -F'[/]' '{print $4}' > /tmp/softcamRuningCheck.tmp")
							sleep(2)

#							open('/tmp/softcamRuningCheck.tmp')
							self.Console.ePopen('ulimit -s 1024;/usr/softcams/' + softcamcheck + " -b")
							sleep(10)
							remove('/tmp/softcamRuningCheck.tmp')
						else:
							self.Console.ePopen('ulimit -s 1024;/usr/softcams/' + softcamcheck)
