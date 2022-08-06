# -*- coding: utf-8 -*-
from . import _
from os import listdir, path
from Plugins.Plugin import PluginDescriptor
from Components.config import config, ConfigBoolean
from . BackupManager import BackupManagerautostart
from . ImageManager import ImageManagerautostart
from . SwapManager import SwapAutostart
from . SoftcamManager import SoftcamAutostart
from . ScriptRunner import ScriptRunnerAutostart
from . IPKInstaller import OpkgInstaller
from . ClientModeBox import ClientModeBoxWizard
from Components.SystemInfo import BoxInfo

config.misc.restorewizardrun = ConfigBoolean(default=False)


def setLanguageFromBackup(backupfile):
	try:
		print(backupfile)
		import tarfile
		tar = tarfile.open(backupfile)
		for member in tar.getmembers():
			if member.name == 'etc/enigma2/settings':
				for line in tar.extractfile(member):
					if line.startswith('config.osd.language'):
						print(line)
						languageToSelect = line.strip().split('=')[1]
						print(languageToSelect)
						if languageToSelect:
							from Components.Language import language
							language.activateLanguage(languageToSelect)
							break
		tar.close()
	except:
		pass


def checkConfigBackup():
	try:
		devmounts = []
		list = []
		files = []
		for dir in ["/media/%s/backup" % media for media in listdir("/media/") if path.isdir(path.join("/media/", media))]:
			devmounts.append(dir)
		if len(devmounts):
			for devpath in devmounts:
				if path.exists(devpath):
					try:
						files = listdir(devpath)
					except:
						files = []
				else:
					files = []
				if len(files):
					for file in files:
						if file.endswith('.tar.gz') and "vision" in file.lower():
							list.append((path.join(devpath, file)))
		if len(list):
			print('[Vision] Backup image:', list[0])
			backupfile = list[0]
			if path.isfile(backupfile):
				setLanguageFromBackup(backupfile)
			return True
		else:
			return None
	except IOError as e:
		print("[Vision] Unable to use device (%s)..." % str(e))
		return None


if config.misc.firstrun.value and not config.misc.restorewizardrun.value:
	if checkConfigBackup() is None:
		backupAvailable = 0
	else:
		backupAvailable = 1


def VISIONMenu(session):
	from .import ui
	return ui.VISIONMenu(session)


def UpgradeMain(session, **kwargs):
	session.open(VISIONMenu)


def startSetup(menuid):
	if menuid != "mainmenu":
		return []
	return [(_("Vision Core"), UpgradeMain, "vision_menu", 1)]


def RestoreWizard(*args, **kwargs):
	from .RestoreWizard import RestoreWizard
	return RestoreWizard(*args, **kwargs)


def SoftcamManager(session):
	from .SoftcamManager import VISIONSoftcamManager
	return VISIONSoftcamManager(session)


def SoftcamMenu(session, **kwargs):
	session.open(SoftcamManager)


def SoftcamSetup(menuid):
	if menuid == "cam":
		return [(_("Vision Softcam"), SoftcamMenu, "softcamsetup", 1005)]
	return []


def BackupManager(session):
	from .BackupManager import VISIONBackupManager
	return VISIONBackupManager(session)


def BackupManagerMenu(session, **kwargs):
	session.open(BackupManager)


def ImageManager(session):
	from .ImageManager import VISIONImageManager
	return VISIONImageManager(session)


def ImageMangerMenu(session, **kwargs):
	session.open(ImageManager)


if BoxInfo.getItem("HasH9SD"):
	def H9SDmanager(session):
		from .H9SDmanager import H9SDmanager
		return H9SDmanager(session)

	def H9SDmanagerMenu(session, **kwargs):
		session.open(H9SDmanager)


def MountManager(session):
	from .MountManager import VISIONDevicesPanel
	return VISIONDevicesPanel(session)


def MountManagerMenu(session, **kwargs):
	session.open(MountManager)


def ScriptRunner(session):
	from .ScriptRunner import VISIONScriptRunner
	return VISIONScriptRunner(session)


def ScriptRunnerMenu(session, **kwargs):
	session.open(ScriptRunner)


def SwapManager(session):
	from .SwapManager import VISIONSwap
	return VISIONSwap(session)


def SwapManagerMenu(session, **kwargs):
	session.open(SwapManager)


def ClientModeBoxMenu(session, **kwargs):
	session.open(ClientModeBox)


def filescan_open(list, session, **kwargs):
	filelist = [x.path for x in list]
	session.open(OpkgInstaller, filelist)  # list


def filescan(**kwargs):
	from Components.Scanner import Scanner, ScanPath
	return Scanner(mimetypes=["application/x-debian-package"],
				paths_to_scan=[
					ScanPath(path="ipk", with_subdirs=True),
					ScanPath(path="", with_subdirs=False),
				],
				name="Opkg",
				description=_("Install extensions."),
				openfnc=filescan_open)


def Plugins(**kwargs):
	plist = [PluginDescriptor(where=PluginDescriptor.WHERE_MENU, needsRestart=False, fnc=startSetup),
			 PluginDescriptor(name=_("Vision Core"), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=UpgradeMain),
			 PluginDescriptor(where=PluginDescriptor.WHERE_MENU, fnc=SoftcamSetup)]
	if config.softcammanager.showinextensions.value:
		plist.append(PluginDescriptor(name=_("Vision Softcam"), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=SoftcamMenu))
	if config.scriptrunner.showinextensions.value:
		plist.append(PluginDescriptor(name=_("Vision Script Runner"), where=PluginDescriptor.WHERE_EXTENSIONSMENU, fnc=ScriptRunnerMenu))
	plist.append(PluginDescriptor(where=PluginDescriptor.WHERE_AUTOSTART, fnc=SoftcamAutostart))
	plist.append(PluginDescriptor(where=PluginDescriptor.WHERE_AUTOSTART, fnc=SwapAutostart))
	plist.append(PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=ImageManagerautostart))
	plist.append(PluginDescriptor(where=PluginDescriptor.WHERE_SESSIONSTART, fnc=BackupManagerautostart))
	if config.misc.firstrun.value and not config.misc.restorewizardrun.value and backupAvailable == 1:
		plist.append(PluginDescriptor(name=_("Restore wizard"), where=PluginDescriptor.WHERE_WIZARD, needsRestart=False, fnc=(0, RestoreWizard)))
	plist.append(PluginDescriptor(name=_("Opkg"), where=PluginDescriptor.WHERE_FILESCAN, needsRestart=False, fnc=filescan))
	plist.append(PluginDescriptor(name=_("Vision Backup Manager"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=BackupManagerMenu))
	plist.append(PluginDescriptor(name=_("Vision Image Manager"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=ImageMangerMenu))
	plist.append(PluginDescriptor(name=_("Vision Mount Manager"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=MountManagerMenu))
	plist.append(PluginDescriptor(name=_("Vision Script Runner"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=ScriptRunnerMenu))
	plist.append(PluginDescriptor(name=_("Vision SWAP Manager"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=SwapManagerMenu))
	plist.append(PluginDescriptor(name=_("Vision Client Mode Box"), where=PluginDescriptor.WHERE_VISIONMENU, fnc=ClientModeBoxMenu))
	return plist
