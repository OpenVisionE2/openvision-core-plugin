# -*- coding: utf-8 -*-
from . import _
from os import listdir, stat
from os.path import isfile, isdir, join, exists
from Components.Console import Console
from Components.Pixmap import Pixmap
from Components.Sources.StaticText import StaticText
from Screens.WizardLanguage import WizardLanguage
from Screens.HelpMenu import ShowRemoteControl
from Screens.MessageBox import MessageBox
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Components.SystemInfo import BoxInfo
from Tools.Multiboot import getCurrentImage

currentkernelversion = BoxInfo.getItem("kernel")
visionversion = BoxInfo.getItem("imgversion")
visionrevision = BoxInfo.getItem("imgrevision")
currentimageversion = str(visionversion) + "-" + str(visionrevision)


class RestoreWizard(WizardLanguage, ShowRemoteControl):
	def __init__(self, session):
		self.xmlfile = resolveFilename(SCOPE_PLUGINS, "SystemPlugins/Vision/restorewizard.xml")
		WizardLanguage.__init__(self, session, showSteps=False, showStepSlider=False)
		ShowRemoteControl.__init__(self)
		self.setTitle(_("Vision Core Restore Wizard"))
		self.skinName = ["NetworkWizard"]
		self.session = session
		self["wizard"] = Pixmap()
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Let's define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))
		self.selectedAction = None
		self.NextStep = None
		self.Text = None
		self.buildListRef = None
		self.didSettingsRestore = False
		self.didPluginRestore = False
		self.PluginsRestore = False
		self.fullbackupfilename = None
		self.delaymess = None
		self.selectedDevice = None
		self.Console = Console()

	def getTranslation(self, text):
		return _(text)

	def listDevices(self):
		devmounts = []
		list = []
		files = []
		mtimes = []
		defaultprefix = BoxInfo.getItem("distro")[4:]

		for dir in ["/media/%s/backup" % media for media in listdir("/media/") if isdir(join("/media/", media))]:
			devmounts.append(dir)
		if len(devmounts):
			for devpath in devmounts:
				if exists(devpath):
					try:
						files = listdir(devpath)
					except:
						files = []
				else:
					files = []
				if len(files):
					for file in files:
						if file.endswith(".tar.gz") and "vision" in file.lower() or file.startswith("%s" % defaultprefix):
							mtimes.append((join(devpath, file), stat(join(devpath, file)).st_mtime)) # (filname, mtime)
		for file in [x[0] for x in sorted(mtimes, key=lambda x: x[1], reverse=True)]: # sort by mtime
			list.append((file, file))
		return list

	def settingsdeviceSelectionMade(self, index):
		self.selectedAction = index
		self.settingsdeviceSelect(index)

	def settingsdeviceSelect(self, index):
		self.selectedDevice = index
		self.fullbackupfilename = index
		self.NextStep = 'settingrestorestarted'

	def settingsdeviceSelectionMoved(self):
		self.settingsdeviceSelect(self.selection)

	def pluginsdeviceSelectionMade(self, index):
		self.selectedAction = index
		self.pluginsdeviceSelect(index)

	def pluginsdeviceSelect(self, index):
		self.selectedDevice = index
		self.fullbackupfilename = index
		self.NextStep = 'plugindetection'

	def pluginsdeviceSelectionMoved(self):
		self.pluginsdeviceSelect(self.selection)

	def markDone(self):
		pass

	def listAction(self):
		list = [(_("OK, to perform a restore"), "settingsquestion"), (_("Exit the restore wizard"), "end")]
		return list

	def listAction2(self):
		list = [(_("Yes, to restore settings"), "settingsrestore"), (_("No, do not restore settings"), "pluginsquestion")]
		return list

	def listAction3(self):
		list = []
		if self.didSettingsRestore:
			list.append((_("Yes, to restore plugins"), "pluginrestore"))
			list.append((_("No, do not restore plugins"), "reboot"))
		else:
			list.append((_("Yes, to restore plugins"), "pluginsrestoredevice"))
			list.append((_("No, do not restore plugins"), "end"))
		return list

	def rebootAction(self):
		list = [(_("OK"), "reboot")]
		return list

	def ActionSelectionMade(self, index):
		self.selectedAction = index
		self.ActionSelect(index)

	def ActionSelect(self, index):
		self.NextStep = index

	def ActionSelectionMoved(self):
		self.ActionSelect(self.selection)

	def buildList(self, action):
		if self.NextStep == 'reboot':
			if BoxInfo.getItem("hasKexec"):
				slot = getCurrentImage()
			if self.didSettingsRestore:
				self.Console.ePopen("tar -xzvf " + self.fullbackupfilename + " -C /" + " etc/enigma2/settings")
			kille2reboot = "sleep 10 && killall -9 enigma2 && init 6"
			self.Console.ePopen("%s" % kille2reboot, self.session.open(MessageBox, _("Finishing restore, your receiver go to restart."), MessageBox.TYPE_INFO))
		elif self.NextStep == 'settingsquestion' or self.NextStep == 'settingsrestore' or self.NextStep == 'pluginsquestion' or self.NextStep == 'pluginsrestoredevice' or self.NextStep == 'end' or self.NextStep == 'noplugins':
			self.buildListfinishedCB(False)
		elif self.NextStep == 'settingrestorestarted':
			self.Console.ePopen("tar -xzvf " + self.fullbackupfilename + " -C / tmp/ExtraInstalledPlugins tmp/backupkernelversion tmp/backupimageversion", self.settingsRestore_Started)
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Please wait while the system gathers information..."), type=MessageBox.TYPE_INFO, enable_input=False)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif self.NextStep == 'plugindetection':
			print('[RestoreWizard] Stage 2: Restoring plugins')
			self.Console.ePopen("tar -xzvf " + self.fullbackupfilename + " -C / tmp/ExtraInstalledPlugins tmp/backupkernelversion tmp/backupimageversion", self.pluginsRestore_Started)
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Please wait while the system gathers information..."), type=MessageBox.TYPE_INFO, enable_input=False)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif self.NextStep == 'pluginrestore':
			if self.feeds == 'OK':
				print('[RestoreWizard] Stage 6: Feeds OK, restoring plugins')
				print('[RestoreWizard] Console command: ', 'opkg install ' + self.pluginslist + ' ' + self.pluginslist2)
				self.Console.ePopen("opkg install " + self.pluginslist + ' ' + self.pluginslist2, self.pluginsRestore_Finished)
				self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Please wait while plugins restore completes..."), type=MessageBox.TYPE_INFO, enable_input=False)
				self.buildListRef.setTitle(_("Restore wizard"))
			elif self.feeds == 'DOWN':
				print('[RestoreWizard] Stage 6: Feeds down')
				self.didPluginRestore = True
				self.NextStep = 'reboot'
				self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Sorry the feeds are down for maintenance. Please try using Backup manager to restore plugins later."), type=MessageBox.TYPE_INFO, timeout=30)
				self.buildListRef.setTitle(_("Restore wizard"))
			elif self.feeds == 'BAD':
				print('[RestoreWizard] Stage 6: No network')
				self.didPluginRestore = True
				self.NextStep = 'reboot'
				self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Your receiver is not connected to the Internet. Please try using Backup manager to restore plugins later."), type=MessageBox.TYPE_INFO, timeout=30)
				self.buildListRef.setTitle(_("Restore wizard"))
			elif self.feeds == 'ERROR':
				self.NextStep = 'pluginrestore'
				self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Background update check is in progress, please try again."), type=MessageBox.TYPE_INFO, timeout=10)
				self.buildListRef.setTitle(_("Restore wizard"))

	def buildListfinishedCB(self, data):
		# self.buildListRef = None
		if data is True:
			self.currStep = self.getStepWithID(self.NextStep)
			self.afterAsyncCode()
		else:
			self.currStep = self.getStepWithID(self.NextStep)
			self.afterAsyncCode()

	def settingsRestore_Started(self, result, retval, extra_args=None):
		self.doRestoreSettings1()

	def doRestoreSettings1(self):
		print('[RestoreWizard] Stage 1: Check version')
		if isfile('/tmp/backupkernelversion'):
			kernelversion = open('/tmp/backupkernelversion').read()
			print('[RestoreWizard] Current kernelversion:', kernelversion)
			if kernelversion == str(currentkernelversion):
				print('[RestoreWizard] Stage 1: Kernel version OK')
				self.doRestoreSettings2()
			else:
				print('[RestoreWizard] Stage 1: Kernel version is different')
				self.noVersion = self.session.openWithCallback(self.doNoVersion, MessageBox, _("Sorry, but the file is not compatible with this kernel version."), type=MessageBox.TYPE_INFO, timeout=30)
				self.noVersion.setTitle(_("Restore wizard"))
		else:
			print('[RestoreWizard] Stage 1: No kernel version to check')
			self.noVersion = self.session.openWithCallback(self.doNoVersion, MessageBox, _("Sorry, but the file is not compatible with this kernel version."), type=MessageBox.TYPE_INFO, timeout=30)
			self.noVersion.setTitle(_("Restore wizard"))

	def doNoVersion(self, result=None, retval=None, extra_args=None):
		self.buildListRef.close(True)

	def doRestoreSettings2(self):
		print('[RestoreWizard] Stage 2: Restoring settings')
		self.Console.ePopen("tar -xzvf " + self.fullbackupfilename + " -C /", self.settingRestore_Finished)
		self.pleaseWait = self.session.open(MessageBox, _("Please wait while settings restore completes..."), type=MessageBox.TYPE_INFO, enable_input=False)
		self.pleaseWait.setTitle(_("Restore wizard"))

	def settingRestore_Finished(self, result, retval, extra_args=None):
		self.didSettingsRestore = True
		network = [x.split(" ")[3] for x in open("/etc/network/interfaces").read().splitlines() if x.startswith("iface eth0")]
		self.pleaseWait.close()
		self.doRestorePlugins1()

	def pluginsRestore_Started(self, result, retval, extra_args=None):
		self.doRestorePlugins1()

	def pluginsRestore_Finished(self, result, retval, extra_args=None):
		from six import ensure_str
		result = ensure_str(result)
		if result:
			print("[RestoreWizard] opkg install result:\n", result)
		self.didPluginRestore = True
		self.NextStep = 'reboot'
		self.buildListRef.close(True)

	def doRestorePlugins1(self):
		print('[RestoreWizard] Stage 3: Check Kernel')
		if isfile('/tmp/backupkernelversion') and isfile('/tmp/backupimageversion'):
			imageversion = open('/tmp/backupimageversion').read()
			kernelversion = open('/tmp/backupkernelversion').read()
			print('[RestoreWizard] Backup image:', imageversion)
			print('[RestoreWizard] Current image:', currentimageversion)
			print('[RestoreWizard] Backup kernel:', kernelversion)
			print('[RestoreWizard] Current kernel:', str(currentkernelversion))
			if kernelversion == str(currentkernelversion):
				print('[RestoreWizard] Stage 3: Kernel and image version are OK')
				self.doRestorePluginsTest()
			else:
				print('[RestoreWizard] Stage 3: Kernel or image version is different')
				if self.didSettingsRestore:
					self.NextStep = 'reboot'
				else:
					self.NextStep = 'noplugins'
				self.buildListRef.close(True)
		else:
			print('[RestoreWizard] Stage 3: No kernel to check')
			if self.didSettingsRestore:
				self.NextStep = 'reboot'
			else:
				self.NextStep = 'noplugins'
			self.buildListRef.close(True)

	def doRestorePluginsTest(self, result=None, retval=None, extra_args=None):
		if self.delaymess:
			self.delaymess.close()
		print('[RestoreWizard] Stage 4: Feeds test')
		self.Console.ePopen('ifdown -v -f eth0; ifup -v eth0 && opkg update', self.doRestorePluginsTestComplete)

	def doRestorePluginsTestComplete(self, result=None, retval=None, extra_args=None):
		result2 = result
		print('[RestoreWizard] Stage 4: Feeds test result', result2)
		if result2.find('wget returned 4') != -1:
			self.NextStep = 'reboot'
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Your receiver is not connected to a network. Please try using the Backup manager to restore plugins later when a network connection is available."), type=MessageBox.TYPE_INFO, timeout=30)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif result2.find('wget returned 8') != -1:
			self.NextStep = 'reboot'
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Your receiver could not connect to the plugin feeds at this time. Please try using the Backup manager to restore plugins later."), type=MessageBox.TYPE_INFO, timeout=30)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif result2.find('bad address') != -1:
			self.NextStep = 'reboot'
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Your receiver is not connected to the Internet. Please try using the Backup manager to restore plugins later."), type=MessageBox.TYPE_INFO, timeout=30)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif result2.find('wget returned 1') != -1 or result2.find('wget returned 255') != -1 or result2.find('404 Not Found') != -1:
			self.NextStep = 'reboot'
			self.buildListRef = self.session.openWithCallback(self.buildListfinishedCB, MessageBox, _("Sorry the feeds are down for maintenance. Please try using the Backup manager to restore plugins later."), type=MessageBox.TYPE_INFO, timeout=30)
			self.buildListRef.setTitle(_("Restore wizard"))
		elif result2.find('Collected errors') != -1:
			print('[RestoreWizard] Stage 4: Update is in progress, delaying')
			self.delaymess = self.session.openWithCallback(self.doRestorePluginsTest, MessageBox, _("A background update check is in progress, please try again."), type=MessageBox.TYPE_INFO, timeout=10)
			self.delaymess.setTitle(_("Restore wizard"))
		else:
			print('[RestoreWizard] Stage 4: Feeds OK')
			self.feeds = 'OK'
			self.doListPlugins()

	def doListPlugins(self):
		print('[RestoreWizard] Stage 4: Feeds test')
		self.Console.ePopen('opkg list-installed', self.doRestorePlugins2)

	def doRestorePlugins2(self, result, retval, extra_args):
		print('[RestoreWizard] Stage 5: Build list of plugins to restore')
		self.pluginslist = ""
		self.pluginslist2 = ""
		plugins = []
		if isfile('/tmp/ExtraInstalledPlugins'):
			self.pluginslist = []
			for line in result.split("\n"):
				if line:
					parts = line.strip().split()
					plugins.append(parts[0])
			tmppluginslist = open('/tmp/ExtraInstalledPlugins', 'r').readlines()
			for line in tmppluginslist:
				if line:
					parts = line.strip().split()
					if len(parts) > 0 and parts[0] not in plugins:
						self.pluginslist.append(parts[0])

		if isfile('/tmp/3rdPartyPlugins'):
			self.pluginslist2 = []
			if isfile('/tmp/3rdPartyPluginsLocation'):
				self.thirdpartyPluginsLocation = open('/tmp/3rdPartyPluginsLocation', 'r').readlines()
				self.thirdpartyPluginsLocation = "".join(self.thirdpartyPluginsLocation)
				self.thirdpartyPluginsLocation = self.thirdpartyPluginsLocation.replace('\n', '')
				self.thirdpartyPluginsLocation = self.thirdpartyPluginsLocation.replace(' ', '%20')
				self.plugfiles = self.thirdpartyPluginsLocation.split('/', 3)
			else:
				self.thirdpartyPluginsLocation = " "

			tmppluginslist2 = open('/tmp/3rdPartyPlugins', 'r').readlines()
			available = None
			for line in tmppluginslist2:
				if line:
					parts = line.strip().split('_')
					if parts[0] not in plugins:
						ipk = parts[0]
						if exists(self.thirdpartyPluginsLocation):
							available = listdir(self.thirdpartyPluginsLocation)
						else:
							devmounts = []
							files = []
							self.plugfile = self.plugfiles[3]
							for dir in ["/media/%s/%s" % (media, self.plugfile) for media in listdir("/media/") if isdir(join("/media/", media))]:
								if media != "autofs" or "net":
									devmounts.append(dir)
							if len(devmounts):
								for x in devmounts:
									print("[BackupManager] Search dir = %s" % devmounts)
									if exists(x):
										self.thirdpartyPluginsLocation = x
										try:
											available = listdir(self.thirdpartyPluginsLocation)
											break
										except:
											continue
						if available:
							for file in available:
								if file:
									fileparts = file.strip().split('_')
									if fileparts[0] == ipk:
										self.thirdpartyPluginsLocation = self.thirdpartyPluginsLocation.replace(' ', '%20')
										ipk = join(self.thirdpartyPluginsLocation, file)
										if exists(ipk):
											self.pluginslist2.append(ipk)

		if len(self.pluginslist) or len(self.pluginslist2):
			self.doRestorePluginsQuestion()
		else:
			if self.didSettingsRestore:
				self.NextStep = 'reboot'
			else:
				self.NextStep = 'noplugins'
			self.buildListRef.close(True)

	def doRestorePluginsQuestion(self):
		if len(self.pluginslist) or len(self.pluginslist2):
			if len(self.pluginslist):
				self.pluginslist = " ".join(self.pluginslist)
			else:
				self.pluginslist = ""
			if len(self.pluginslist2):
				self.pluginslist2 = " ".join(self.pluginslist2)
			else:
				self.pluginslist2 = ""
			print('[RestoreWizard] Stage 6: Plugins to restore in feeds', self.pluginslist)
			print('[RestoreWizard] Stage 6: Plugins to restore in extra location', self.pluginslist2)
			if self.didSettingsRestore:
				print('[RestoreWizard] Stage 6: Proceed to question')
				self.NextStep = 'pluginsquestion'
				self.buildListRef.close(True)
			else:
				print('[RestoreWizard] Stage 6: Proceed to restore')
				self.NextStep = 'pluginrestore'
				self.buildListRef.close(True)
		else:
			print('[RestoreWizard] Stage 6: No plugins to restore')
			if self.didSettingsRestore:
				self.NextStep = 'reboot'
			else:
				self.NextStep = 'noplugins'
		self.buildListRef.close(True)
