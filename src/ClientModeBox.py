# -*- coding: utf-8 -*-
from . import _, PluginLanguageDomain
from Screens.WizardLanguage import WizardLanguage
from enigma import eEPGCache, eDVBDB
from xml.dom import minidom
from re import search
from os import makedirs, walk, remove, mkdir, system
from os.path import exists, isdir, join, dirname, basename
from shutil import copy2, move, rmtree
import locale
from six.moves.urllib.parse import quote, urlencode
from six.moves.urllib.request import urlopen, Request
from six.moves.urllib.error import URLError, HTTPError
from Components.Network import iNetwork
from time import localtime, time, mktime
import socket
import threading
from Components.Console import Console
from Components.Pixmap import Pixmap
from Components.Sources.Boolean import Boolean
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from Screens.Screen import Screen
from Screens.MessageBox import MessageBox
from Tools.Notifications import AddNotificationWithID
from Screens.Standby import TryQuitMainloop
from Components.ActionMap import ActionMap
from Components.Button import Button
from Components.ConfigList import ConfigListScreen
from Components.config import config, getConfigListEntry, ConfigSubsection, ConfigInteger, ConfigYesNo, ConfigText, ConfigClock, ConfigSelection
from Components.Sources.StaticText import StaticText
from enigma import eTimer
from Components.Label import Label
from bisect import insort
from Components.TimerSanityCheck import TimerSanityCheck
from RecordTimer import RecordTimerEntry, AFTEREVENT
from ServiceReference import ServiceReference
from timer import TimerEntry

mountstate = False
mounthost = None
MAX_THREAD_COUNT = 40
timerinstance = None

config.ipboxclient = ConfigSubsection()
config.ipboxclient.host = ConfigText(default="", fixed_size=False)
config.ipboxclient.port = ConfigInteger(default=80, limits=(1, 65535))
config.ipboxclient.streamport = ConfigInteger(default=8001, limits=(1, 65535))
config.ipboxclient.auth = ConfigYesNo(default=False)
config.ipboxclient.firstconf = ConfigYesNo(default=False)
config.ipboxclient.username = ConfigText(default="", fixed_size=False)
config.ipboxclient.password = ConfigText(default="", fixed_size=False)
config.ipboxclient.schedule = ConfigYesNo(default=False)
config.ipboxclient.scheduletime = ConfigClock(default=0) # 1:00
config.ipboxclient.repeattype = ConfigSelection(default="daily", choices=[("daily", _("Daily")), ("weekly", _("Weekly")), ("monthly", _("Monthly"))])
config.ipboxclient.mounthdd = ConfigYesNo(default=False)
config.ipboxclient.remotetimers = ConfigYesNo(default=False)


def getValueFromNode(event, key):
	tmp = event.getElementsByTagName(key)[0].firstChild
	if (tmp):
		return str(tmp.nodeValue)

	return ""


class ClientModeBoxWizard(WizardLanguage):

	skin = """
		<screen name="ClientModeBoxWizard" position="center,center" size="720,576" title="ClientModeBoxWizard" >
			<widget name="text"
					position="65,40"
					size="640,100"
					font="Regular;24" />

			<widget source="list"
					render="Listbox"
					position="65,160"
					size="640,220"
					font="Regular;24"
					scrollbarMode="showOnDemand" >
				<convert type="StringList" />
			</widget>

			<widget name="config"
					position="65,160"
					zPosition="1"
					size="440,220"
					transparent="1"
					font="Regular;24"
					scrollbarMode="showOnDemand" />

			<widget name="step"
					position="65,470"
					zPosition="1"
					size="440,40"
					transparent="1" />

			<widget name="stepslider"
					borderWidth="1"
					position="65,468"
					zPosition="1"
					size="440,40"
					transparent="1" />

			<ePixmap pixmap="buttons/button_red.png"
					 position="35,523"
					 zPosition="0"
					 size="15,16"
					 transparent="1"
					 alphaTest="blend" />

			<widget name="languagetext"
					position="65,520"
					size="300,30"
					font="Regular;18" />
		</screen>"""

	def __init__(self, session):
		self.xmlfile = resolveFilename(SCOPE_PLUGINS, "SystemPlugins/Vision/clientmodebox.xml")
		WizardLanguage.__init__(self, session)
		self.setTitle(_('Vision Client Mode Box'))
		self.skinName = ["ClientModeBoxWizard"]
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))
		self['myactions'] = ActionMap(["MenuActions"], {
			'menu': self.Menu,
			'cancel': self.KeyCancel,
		}, -1)

	def Menu(self, session=None, **kwargs):
		self.session.open(ClientModeBoxMenu, PluginLanguageDomain)

	def KeyCancel(self):
		self.close(True)

	def getTranslation(self, text):
		return _(text)

	def scan(self):
		self.timer = eTimer()
		self.timer.callback.append(self.doscan)
		self.timer.start(100)

	def doscan(self):
		self.timer.stop()
		scanner = ClientModeBoxScan(self.session)
		self.scanresults = scanner.scan()
		if self.scanresults and len(self.scanresults) > 0:
			self.currStep = self.getStepWithID('choose')
		else:
			self.currStep = self.getStepWithID('nodevices')
		self.currStep += 1
		self.updateValues()

	def getScanList(self):
		devices = []
		for result in self.scanresults:
			devices.append((result[0] + ' (' + result[1] + ')', result[1]))

		devices.append((_('Cancel'), 'cancel'))
		return devices

	def selectionMade(self, result):
		selecteddevice = None
		if result != 'cancel':
			for device in self.scanresults:
				if device[1] == result:
					selecteddevice = device
		if selecteddevice:
			config.ipboxclient.host.value = selecteddevice[1]
			config.ipboxclient.host.save()
			config.ipboxclient.port.value = 80
			config.ipboxclient.port.save()
			config.ipboxclient.streamport.value = 8001
			config.ipboxclient.streamport.save()
			config.ipboxclient.auth.value = False
			config.ipboxclient.auth.save()
			config.ipboxclient.firstconf.value = True
			config.ipboxclient.firstconf.save()

			mount = ClientModeBoxMount(self.session)
			mount.remount()

			self.currStep = self.getStepWithID('download')
		else:
			self.currStep = self.getStepWithID('welcome')

	def download(self):
		self.timer = eTimer()
		self.timer.callback.append(self.dodownload)
		self.timer.start(100)

	def dodownload(self):
		self.timer.stop()
		downloader = ClientModeBoxDownloader(self.session)
		try:
			downloader.download()
			self.currStep = self.getStepWithID('end')
		except Exception as e:
			print(str(e))
			self.currStep = self.getStepWithID('nodownload')
		self.currStep += 1
		self.updateValues()


class ScanHost(threading.Thread):
	def __init__(self, ipaddress, port):
		threading.Thread.__init__(self)
		self.ipaddress = ipaddress
		self.port = port
		self.isopen = False

	def run(self):
		serverip = socket.gethostbyname(self.ipaddress)

		try:
			sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			sock.settimeout(10)
			result = sock.connect_ex((serverip, self.port))
			sock.close()
			self.isopen = result == 0

		except socket.gaierror:
			self.isopen = False

		except socket.error:
			self.isopen = False


class ClientModeBoxScan:
	def __init__(self, session):
		self.session = session

	def scan(self):
		print("[ClientModeBox] Network scan started")
		devices = []
		for key in iNetwork.ifaces:
			if iNetwork.ifaces[key]['up']:
				devices += self.scanNetwork(iNetwork.ifaces[key]['ip'], iNetwork.ifaces[key]['netmask'])

		print("[ClientModeBox] Network scan completed. Found " + str(len(devices)) + " devices")
		return devices

	def ipRange(self, start_ip, end_ip):
		temp = start_ip
		ip_range = []

		ip_range.append(".".join(map(str, start_ip)))
		while temp != end_ip:
			start_ip[3] += 1
			for i in (3, 2, 1):
				if temp[i] == 256:
					temp[i] = 0
					temp[i - 1] += 1
			ip_range.append(".".join(map(str, temp)))

		return ip_range

	def getNetSize(self, netmask):
		binary_str = ''
		for octet in netmask:
			binary_str += bin(int(octet))[2:].zfill(8)
		return len(binary_str.rstrip('0'))

	def getBoxName(self, ipaddress):
		try:
			httprequest = urlopen('http://' + ipaddress + '/web/about', timeout=5)
			xmldoc = minidom.parseString(httprequest.read())
			return xmldoc.getElementsByTagName('e2model')[0].firstChild.nodeValue
		except Exception:
			pass
		return None

	def scanNetwork(self, ipaddress, subnet):
		print("[ClientModeBox] Scan interface with IP address", ipaddress, "and subnet", subnet)
		cidr = self.getNetSize(subnet)

		startip = []
		for i in range(4):
			startip.append(int(ipaddress[i]) & int(subnet[i]))

		endip = list(startip)
		brange = 32 - cidr
		for i in range(brange):
			endip[3 - i // 8] = endip[3 - i // 8] + (1 << (i % 8))

		if startip[0] == 0:
			print("[ClientModeBox] Your start IP address seems invalid. Skip interface scan.")
			return []

		startip[3] += 1
		endip[3] -= 1

		print("[ClientModeBox] Scan from IP", startip, "to", endip)

		threads = []
		threads_completed = []
		for iptoscan in self.ipRange(startip, endip):
			if len(threads) >= MAX_THREAD_COUNT:
				scanhost = threads.pop(0)
				scanhost.join()
				threads_completed.append(scanhost)

			scanhost = ScanHost(iptoscan, 80)
			scanhost.start()
			threads.append(scanhost)

		for scanhost in threads:
			scanhost.join()
			threads_completed.append(scanhost)

		devices = []
		for scanhost in threads_completed:
			if scanhost.isopen:
				print("[ClientModeBox] Device with IP " + scanhost.ipaddress + " listen on port 80, check if it's enigma2")
				boxname = self.getBoxName(scanhost.ipaddress)
				if boxname:
					print("[ClientModeBox] Found " + boxname + " on ip " + scanhost.ipaddress)
					devices.append((str(boxname), scanhost.ipaddress))
				else:
					print("[ClientModeBox] No enigma2 found. Skip host")
		return devices


class ClientModeBoxMount:
	def __init__(self, session):
		self.session = session
		self.console = Console()
		if exists('/media/hdd') or system('mount |grep -i /media/hdd') == 0:
			self.mountpoint = '/media/hdd-server'
		if not isdir('/media/hdd'):
			self.mountpoint = '/media/hdd'
		self.share = '/mnt/hdd'

	def automount(self):
		global mountstate
		global mounthost
		mountstate = False
		mounthost = None
		if config.ipboxclient.mounthdd.value:
			if self.isMountPoint(self.mountpoint):
				if not self.umount(self.mountpoint):
					print('Cannot umount ')
					return

			if not self.mount(config.ipboxclient.host.value, self.share, self.mountpoint):
				print('Cannot mount ' + config.ipboxclient.host.value + '/' + self.share + ' to ' + self.mountpoint)
			else:
				mountstate = True
				mounthost = config.ipboxclient.host.value

	def remount(self):
		global mountstate
		global mounthost
		if mountstate and not config.ipboxclient.mounthdd.value:
			self.umount(self.mountpoint)
			mountstate = False
		elif not mountstate and config.ipboxclient.mounthdd.value:
			self.automount()
		elif mountstate and config.ipboxclient.mounthdd.value != mounthost:
			self.automount()

	def isMountPoint(self, path):
		return system('mountpoint ' + path) == 0

	def umount(self, path=None):
		return system('umount ' + path) == 0

	def mount(self, ip, share, path):
		try:
			makedirs(self.mountpoint)
		except Exception:
			pass
		return system('mount -t nfs' + ' ' + ip + ':' + '/' + share + ' ' + path + ' ' + '&&' + ' ' + 'echo -e' + ' ' + '"' + ip + ':' + share + ' ' + path + ' ' + 'nfs nolock,rsize=8192,wsize=8192' + ' ' + '\n"' + ' ' + '>>' + ' ' + '/etc/fstab') == 0


class ClientModeBoxMenu(Screen, ConfigListScreen):
	skin = """
		<screen name="ClientModeBoxMenu" position="100,100" size="560,400">
			<widget name="config"
					position="10,10"
					zPosition="3"
					size="540,270"
					scrollbarMode="showOnDemand"
					transparent="1"/>

			<widget source="text"
					render="Label"
					position="10,290"
					size="540,60"
					font="Regular;20" />

			<widget name="key_red"
					position="0,360"
					size="140,40"
					verticalAlignment="center"
					horizontalAlignment="center"
					zPosition="5"
					transparent="1"
					foregroundColor="white"
					font="Regular;18" />

			<widget name="key_green"
					position="140,360"
					size="140,40"
					verticalAlignment="center"
					horizontalAlignment="center"
					zPosition="5"
					transparent="1"
					foregroundColor="white"
					font="Regular;18" />

			<widget name="key_yellow"
					position="280,360"
					size="140,40"
					verticalAlignment="center"
					horizontalAlignment="center"
					zPosition="5"
					transparent="1"
					foregroundColor="white"
					font="Regular;18" />

			<widget name="key_blue"
					position="420,360"
					size="140,40"
					verticalAlignment="center"
					horizontalAlignment="center"
					zPosition="5"
					transparent="1"
					foregroundColor="white"
					font="Regular;18" />

			<ePixmap name="red"
					 pixmap="buttons/red.png"
					 position="0,360"
					 size="140,40"
					 zPosition="4"
					 transparent="1"
					 alphaTest="blend" />

			<ePixmap name="green"
					 pixmap="buttons/green.png"
					 position="140,360"
					 size="140,40"
					 zPosition="4"
					 transparent="1"
					 alphaTest="blend" />

			<ePixmap name="yellow"
					 pixmap="buttons/yellow.png"
					 position="280,360"
					 size="140,40"
					 zPosition="4"
					 transparent="1"
					 alphaTest="blend" />

			<ePixmap name="blue"
					 pixmap="buttons/blue.png"
					 position="420,360"
					 size="140,40"
					 zPosition="4"
					 transparent="1"
					 alphaTest="blend" />
		</screen>"""

	def __init__(self, session, timerinstance):
		self.session = session
		self.list = []
		self.timerinstance = ClientModeBoxTimer(self.session)
		self.remotetimer_old = config.ipboxclient.remotetimers.value
		Screen.__init__(self, session)
		ConfigListScreen.__init__(self, self.list)
		self.setTitle(_('Vision Client Mode Box'))
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))

		self["VKeyIcon"] = Boolean(False)
		self["text"] = StaticText(_('Important: Do not enable OpenWebif authentication on server, neither in this Setup.'))
		self["key_red"] = Button(_('Cancel'))
		self["key_green"] = Button(_('Save'))
		self["key_yellow"] = Button(_('Scan'))
		self["key_blue"] = Button(_('About'))
		self["actions"] = ActionMap(["OkCancelActions", "ColorActions"], {
			"cancel": self.keyCancel,
			"red": self.closeRecursive,
			"green": self.keySave,
			"yellow": self.keyScan,
			"blue": self.keyAbout
		}, -2)

		self.populateMenu()

		if not config.ipboxclient.firstconf.value:
			self.timer = eTimer()
			self.timer.callback.append(self.scanAsk)
			self.timer.start(100)

	def exit(self):
		self.close(True)

	def scanAsk(self):
		self.timer.stop()
		self.session.openWithCallback(self.scanConfirm, MessageBox, _("Do you want to scan for a server?"), MessageBox.TYPE_YESNO)

	def scanConfirm(self, confirmed):
		if confirmed:
			self.keyScan()

	def populateMenu(self):
		self.list = []
		self.list.append(getConfigListEntry(_("Host"), config.ipboxclient.host))
		self.list.append(getConfigListEntry(_("HTTP port"), config.ipboxclient.port))
		self.list.append(getConfigListEntry(_("Streaming port"), config.ipboxclient.streamport))
		self.list.append(getConfigListEntry(_("Authentication"), config.ipboxclient.auth))
		if config.ipboxclient.auth.value:
			self.list.append(getConfigListEntry(_("Default username (root)"), config.ipboxclient.username))
			self.list.append(getConfigListEntry(_("Password"), config.ipboxclient.password))
		self.list.append(getConfigListEntry(_("Use remote HDD"), config.ipboxclient.mounthdd))
		self.list.append(getConfigListEntry(_("Use remote timers"), config.ipboxclient.remotetimers))
		self.list.append(getConfigListEntry(_("Schedule sync"), config.ipboxclient.schedule))
		if config.ipboxclient.schedule.getValue():
			self.list.append(getConfigListEntry(_("Time of sync to start"), config.ipboxclient.scheduletime))
			self.list.append(getConfigListEntry(_("Repeat how often"), config.ipboxclient.repeattype))

		self["config"].list = self.list
		self["config"].l.setList(self.list)

	def keyLeft(self):
		ConfigListScreen.keyLeft(self)
		self.populateMenu()

	def keyRight(self):
		ConfigListScreen.keyRight(self)
		self.populateMenu()

	def keySave(self):
		for x in self["config"].list:
			x[1].save()
		config.ipboxclient.firstconf.value = True
		config.ipboxclient.firstconf.save()
		if self.timerinstance:
			self.timerinstance.refreshScheduler()

		mount = ClientModeBoxMount(self.session)
		mount.remount()

		self.messagebox = self.session.open(MessageBox, _('Please wait while download is in progress.\nNote: If you have parental control enabled on remote box, the local settings will be overwritten.'), MessageBox.TYPE_INFO, enable_input=False)
		self.timer = eTimer()
		self.timer.callback.append(self.download)
		self.timer.start(100)

	def closeRecursive(self):
		self.close(True)

	def keyAbout(self):
		self.session.open(ClientModeBoxAbout)

	def keyScan(self):
		self.messagebox = self.session.open(MessageBox, _('Please wait while scan is in progress.\nThis operation may take a while'), MessageBox.TYPE_INFO, enable_input=False)
		self.timer = eTimer()
		self.timer.callback.append(self.scan)
		self.timer.start(100)

	def scan(self):
		self.timer.stop()
		scanner = ClientModeBoxScan(self.session)
		self.scanresults = scanner.scan()
		self.messagebox.close()
		self.timer = eTimer()
		self.timer.callback.append(self.parseScanResults)
		self.timer.start(100)

	def parseScanResults(self):
		self.timer.stop()
		if len(self.scanresults) > 0:
			menulist = []
			for result in self.scanresults:
				menulist.append((result[0] + ' (' + result[1] + ')', result))
			menulist.append((_('Cancel'), None))
			message = _("Choose your main device")
			self.session.openWithCallback(self.scanCallback, MessageBox, message, list=menulist)
		else:
			self.session.open(MessageBox, _("No devices found"), type=MessageBox.TYPE_ERROR)

	def scanCallback(self, result):
		if (result):
			config.ipboxclient.host.value = result[1]
			config.ipboxclient.host.save()
			config.ipboxclient.port.value = 80
			config.ipboxclient.port.save()
			config.ipboxclient.streamport.value = 8001
			config.ipboxclient.streamport.save()
			config.ipboxclient.auth.value = False
			config.ipboxclient.auth.save()
			config.ipboxclient.firstconf.value = True
			config.ipboxclient.firstconf.save()

			mount = ClientModeBoxMount(self.session)
			mount.remount()

			self.populateMenu()

	def download(self):
		self.timer.stop()
		downloader = ClientModeBoxDownloader(self.session)
		try:
			downloader.download()
			self.messagebox.close()
			self.timer = eTimer()
			self.timer.callback.append(self.downloadCompleted)
			self.timer.start(100)
		except Exception as e:
			print(str(e))
			self.messagebox.close()
			self.timer = eTimer()
			self.timer.callback.append(self.downloadError)
			self.timer.start(100)

	def restart(self, response):
		if response:
			self.session.open(TryQuitMainloop, 3)
		else:
			self.close()

	def downloadCompleted(self):
		self.timer.stop()
		if self.remotetimer_old != config.ipboxclient.remotetimers.value:
			self.session.openWithCallback(self.restart, MessageBox, _("To apply new settings, you need to restart GUI your STB. Do you want restart it now?"), type=MessageBox.TYPE_YESNO)
		else:
			self.session.openWithCallback(self.close, MessageBox, _("Download completed"), type=MessageBox.TYPE_INFO)

	def downloadError(self):
		self.timer.stop()
		self.session.open(MessageBox, _("Cannot download data. Please check your configuration"), type=MessageBox.TYPE_ERROR)


class ClientModeBoxDownloader:
	DIR_ENIGMA2 = "/etc/enigma2/"
	DIR_HDD = "/media/hdd/"
	DIR_USB = "/media/usb/"
	DIR_TMP = "/tmp/"

	def __init__(self, session):
		self.session = session

	def download(self):
		baseurl = "http://"
		if config.ipboxclient.auth.value:
			baseurl += config.ipboxclient.username.value
			baseurl += ":"
			baseurl += config.ipboxclient.password.value
			baseurl += "@"

		baseurl += config.ipboxclient.host.value
		baseurl += ":"

		streamingurl = baseurl

		baseurl += str(config.ipboxclient.port.value)
		streamingurl += str(config.ipboxclient.streamport.value)

		print("[ClientModeBox] Web interface URL: " + baseurl)
		print("[ClientModeBox] Streaming URL: " + streamingurl)

		for stype in ["tv", "radio"]:
			print("[ClientModeBox] Download " + stype + " bouquets from " + baseurl)
			bouquets = self.downloadBouquets(baseurl, stype)
			print("[ClientModeBox] Save " + stype + " bouquets from " + streamingurl)
			self.saveBouquets(bouquets, streamingurl, '/etc/enigma2/bouquets.' + stype)

		print("[ClientModeBox] Reload bouquets")
		self.reloadBouquets()

		print("[ClientModeBox] Sync EPG")
		self.downloadEPG(baseurl)

		print("[ClientModeBox] Sync parental control")
		self.downloadParentalControl(baseurl)

		print("[ClientModeBox] Sync is done!")

	def getSetting(self, baseurl, key):
		httprequest = urlopen(baseurl + '/web/settings')
		xmldoc = minidom.parseString(httprequest.read())
		settings = xmldoc.getElementsByTagName('e2setting')
		for setting in settings:
			if getValueFromNode(setting, 'e2settingname') == key:
				return getValueFromNode(setting, 'e2settingvalue')

		return None

	def getEPGLocation(self, baseurl):
		return self.getSetting(baseurl, 'config.misc.epgcache_filename')

	def getParentalControlEnabled(self, baseurl):
		return self.getSetting(baseurl, 'config.ParentalControl.servicepinactive') == 'true'

	def getParentalControlType(self, baseurl):
		value = self.getSetting(baseurl, 'config.ParentalControl.type')
		if not value:
			value = 'blacklist'
		return value

	def getParentalControlPinState(self, baseurl):
		return self.getSetting(baseurl, 'config.ParentalControl.servicepinactive') == 'true'

	def getParentalControlPin(self, baseurl):
		value = self.getSetting(baseurl, 'config.ParentalControl.servicepin.0')
		if not value:
			value = "0000"
		return int(value)

	def downloadParentalControlBouquets(self, baseurl):
		bouquets = []
		httprequest = urlopen(baseurl + '/web/parentcontrollist')
		xmldoc = minidom.parseString(httprequest.read())
		services = xmldoc.getElementsByTagName('e2service')
		for service in services:
			bouquet = {}
			bouquet['reference'] = getValueFromNode(service, 'e2servicereference')
			bouquet['name'] = getValueFromNode(service, 'e2servicename')

			bouquets.append(bouquet)

		return bouquets

	def downloadBouquets(self, baseurl, stype):
		scriptLocale = locale.setlocale(category=locale.LC_ALL, locale="en_GB.UTF-8")
		bouquets = []
		httprequest = urlopen(baseurl + '/web/bouquets?stype=' + stype)
		print("[ClientModeBox] Download bouquets from " + baseurl + '/web/bouquets?stype=' + stype)
		xmldoc = minidom.parseString(httprequest.read())
		services = xmldoc.getElementsByTagName('e2service')
		for service in services:
			bouquet = {}
			bouquet['reference'] = getValueFromNode(service, 'e2servicereference')
			bouquet['name'] = getValueFromNode(service, 'e2servicename')
			bouquet['services'] = []

			httprequest = urlopen(baseurl + '/web/getservices?' + urlencode({'sRef': bouquet['reference']}) + '&hidden=1')
			xmldoc2 = minidom.parseString(httprequest.read())
			services2 = xmldoc2.getElementsByTagName('e2service')
			for service2 in services2:
				ref = ""
				tmp = getValueFromNode(service2, 'e2servicereference')
				cnt = 0
				for x in tmp:
					ref += x
					if x == ':':
						cnt += 1
					if cnt == 10:
						break

				bouquet['services'].append({
					'reference': ref,
					'name': getValueFromNode(service2, 'e2servicename')
				})

			bouquets.append(bouquet)

		return bouquets

	def saveBouquets(self, bouquets, streamingurl, destinationfile):
		bouquetsfile = open(destinationfile, "w")
		bouquetsfile.write("#NAME Bouquets (TV)" + "\n")
		print("[ClientModeBox] Stream URL " + streamingurl)
		for bouquet in bouquets:
			pattern = r'"([A-Za-z0-9_\./\\-]*)"'
			m = search(pattern, bouquet['reference'])
			if not m:
				continue

			filename = m.group().strip("\"")
			bouquetsfile.write("#SERVICE " + bouquet['reference'] + "\n")
			outfile = open("/etc/enigma2/" + filename, "w")
			outfile.write("#NAME " + bouquet['name'] + "\n")
			for service in bouquet['services']:
				tmp = service['reference'].split(':')
				isDVB = False
				isStreaming = False
				url = ""

				if len(tmp) > 1 and tmp[0] == '1' and tmp[1] == '0':
					if len(tmp) > 10 and tmp[10].startswith('http%3a//'):
						isStreaming = True
					else:
						isDVB = True
						url = streamingurl + "/" + service['reference']

				if isDVB:
					outfile.write("#SERVICE " + service['reference'] + quote(url) + ":" + service['name'] + "\n")
				elif isStreaming:
					outfile.write("#SERVICE " + service['reference'] + "\n")
				else:
					outfile.write("#SERVICE " + service['reference'] + "\n")
					outfile.write("#DESCRIPTION " + service['name'] + "\n")
			outfile.close()
		bouquetsfile.close()

	def reloadBouquets(self):
		baseurl = "http://"
		baseurl += config.ipboxclient.host.value
		db = eDVBDB.getInstance()
		db.reloadServicelist()
		db.reloadBouquets()
		AddNotificationWithID("ClientModeBoxChannelsImportOK", MessageBox, _("Channels imported successfully from %s") % baseurl, type=MessageBox.TYPE_INFO, timeout=5)

	def downloadEPGFTP(self, baseurl):
		print("[ClientModeBox] downloadEPGFTP Force EPG save on remote receiver...")
		self.forceSaveEPGonRemoteReceiver(baseurl)
		print("[ClientModeBox] downloadEPGFTP Searching for epg.dat...")
		result = self.FTPdownloadFile(self.DIR_ENIGMA2, "settings", "settings")
		if result:
			self.checkEPGCallback()
		else:
			print("EPG not received from server")

	def forceSaveEPGonRemoteReceiver(self, baseurl):
		urlserver = "%s/api/saveepg" % baseurl.replace(":80", "")
		print('[ClientModeBox] saveEPGonRemoteReceiver URL: %s' % urlserver)
		try:
			req = Request(urlserver)
			response = urlopen(req, timeout=timeout)
			print('[ClientModeBox] saveEPGonRemoteReceiver Response: %d, %s' % (response.getcode(), response.read().strip().replace("\r", "").replace("\n", "")))
		except HTTPError as err:
			print('[ClientModeBox] saveEPGonRemoteReceiver ERROR: %s', err)
		except URLError as err:
			print('[ClientModeBox] saveEPGonRemoteReceiver ERROR: %s', err)
		except:
			print('[ClientModeBox] saveEPGonRemoteReceiver undefined error')

	def FTPdownloadFile(self, sourcefolder, sourcefile, destfile):
		serverip = ""
		serverip += config.ipboxclient.host.value
		print("[ClientModeBox] Downloading remote file '%s'" % sourcefile)
		try:
			from ftplib import FTP
			ftp = FTP()
			ftp.set_pasv(config.clientmode.passive.value)
			ftp.connect(host=serverip, port=config.clientmode.serverFTPPort.value, timeout=5)
			ftp.login(user=config.clientmode.serverFTPusername.value, passwd=config.clientmode.serverFTPpassword.value)
			ftp.cwd(sourcefolder)
			with open(self.DIR_TMP + destfile, 'wb') as f:
				result = ftp.retrbinary('RETR %s' % sourcefile, f.write)
				ftp.quit()
				f.close()
				if result.startswith("226"):
					return True
			return False
		except Exception as err:
			print("[ClientModeBox] FTPdownloadFile Error:", err)
			return False

	def removeFiles(self, targetdir, target):
		targetLen = len(target)
		for root, dirs, files in walk(targetdir):
			for name in files:
				if target in name[:targetLen]:
					remove(join(root, name))

	def checkEPGCallback(self):
		baseurl = "http://"
		baseurl += config.ipboxclient.host.value
		try:
			self.remoteEPGpath = self.DIR_ENIGMA2
			self.remoteEPGfile = "epg"
			self.remoteEPGfile = "%s.dat" % self.remoteEPGfile.replace('.dat', '')
			print("[ClientModeBox] Remote EPG filename. '%s%s'" % (self.remoteEPGpath, self.remoteEPGfile))
			result = self.FTPdownloadFile(self.remoteEPGpath, self.remoteEPGfile, "epg.dat")
			if result:
				self.importEPGCallback()
			else:
				print("[ClientModeBox] Remote EPG filename not path in internal flash")
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)
		try:
			self.remoteEPGpath = self.DIR_HDD
			self.remoteEPGfile = "epg"
			self.remoteEPGfile = "%s.dat" % self.remoteEPGfile.replace('.dat', '')
			print("[ClientModeBox] Remote EPG filename. '%s%s'" % (self.remoteEPGpath, self.remoteEPGfile))
			result = self.FTPdownloadFile(self.remoteEPGpath, self.remoteEPGfile, "epg.dat")
			if result:
				self.importEPGCallback()
			else:
				print("[ClientModeBox] Remote EPG filename not path in HDD")
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)
		try:
			self.remoteEPGpath = self.DIR_USB
			self.remoteEPGfile = "epg"
			self.remoteEPGfile = "%s.dat" % self.remoteEPGfile.replace('.dat', '')
			print("[ClientModeBox] Remote EPG filename. '%s%s'" % (self.remoteEPGpath, self.remoteEPGfile))
			result = self.FTPdownloadFile(self.remoteEPGpath, self.remoteEPGfile, "epg.dat")
			if result:
				self.importEPGCallback()
			else:
				print("[ClientModeBox] Remote EPG filename not path in USB")
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)

	def copyFile(self, source, dest):
		copy2(source, dest)

	def importEPGCallback(self):
		baseurl = "http://"
		baseurl += config.ipboxclient.host.value
		print("[ClientModeBox] importEPGCallback '%s%s' downloaded successfully from server." % (self.remoteEPGpath, self.remoteEPGfile))
		print("[ClientModeBox] importEPGCallback Removing current EPG data...")
		try:
			remove(config.misc.epgcache_filename.value)
		except OSError:
			pass
		self.copyFile(self.DIR_TMP + "epg.dat", config.misc.epgcache_filename.value)
		self.removeFiles(self.DIR_TMP, "epg.dat")
		eEPGCache.getInstance().load()
		print("[ClientModeBox] importEPGCallback New EPG data loaded...")
		print("[ClientModeBox] importEPGCallback Closing importer.")
		AddNotificationWithID("ClientModeBoxEPGImportOK", MessageBox, _("EPG imported successfully from %s") % baseurl, type=MessageBox.TYPE_INFO, timeout=5)

	def downloadEPG(self, baseurl):
		from json import loads
		try:
			urlopen("%s/web/saveepg" % baseurl, timeout=5)
		except Exception as err:
			print("[ClientModeBox] %s" % err)
		print("[ClientModeBox] Get EPG Location")
		try:
			epgdatfile = "/etc/enigma2/epg.dat"
			files = [file for file in loads(urlopen("%s/file?dir=%s" % (baseurl, dirname(epgdatfile)), timeout=5).read())["files"] if basename(file).startswith("epg.dat")]
			epg_location = files[0] if files else None
			if epg_location:
				print("[ClientModeBox] Copy EPG file from %s" % baseurl)
				try:
					try:
						mkdir("/tmp/epgdat")
					except:
						print("[ClientModeBox] epgdat folder exists in tmp")
					epgdattmp = "/tmp/epgdat"
					epgdatserver = "/tmp/epgdat/epg.dat"
					open("%s/%s" % (epgdattmp, basename(epg_location)), "wb").write(urlopen("%s/file?file=%s" % (baseurl, epg_location), timeout=5).read())
					if "epg.dat" in (epgdatserver):
						move("%s" % epgdatserver, "%s" % (config.misc.epgcache_filename.value))
						eEPGCache.getInstance().load()
						rmtree(epgdattmp)
						AddNotificationWithID("ClientModeBoxEPGImportOK", MessageBox, _("EPG imported successfully from %s") % baseurl, type=MessageBox.TYPE_INFO, timeout=5)
				except Exception as err:
					print("[ClientModeBox] cannot save EPG %s" % err)
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)
			return self.downloadEPGFTP(baseurl)
		try:
			epgdatfile = "/media/hdd/epg.dat"
			files = [file for file in loads(urlopen("%s/file?dir=%s" % (baseurl, dirname(epgdatfile)), timeout=5).read())["files"] if basename(file).startswith("epg.dat")]
			epg_location = files[0] if files else None
			if epg_location:
				print("[ClientModeBox] Copy EPG file from %s" % baseurl)
				try:
					try:
						mkdir("/tmp/epgdat")
					except:
						print("[ClientModeBox] epgdat folder exists in tmp")
					epgdattmp = "/tmp/epgdat"
					epgdatserver = "/tmp/epgdat/epg.dat"
					open("%s/%s" % (epgdattmp, basename(epg_location)), "wb").write(urlopen("%s/file?file=%s" % (baseurl, epg_location), timeout=5).read())
					if "epg.dat" in (epgdatserver):
						move("%s" % epgdatserver, "%s" % (config.misc.epgcache_filename.value))
						eEPGCache.getInstance().load()
						rmtree(epgdattmp)
						AddNotificationWithID("ClientModeBoxEPGImportOK", MessageBox, _("EPG imported successfully from %s") % baseurl, type=MessageBox.TYPE_INFO, timeout=5)
				except Exception as err:
					print("[ClientModeBox] cannot save EPG %s" % err)
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)
			return self.downloadEPGFTP(baseurl)
		try:
			epgdatfile = "/media/usb/epg.dat"
			files = [file for file in loads(urlopen("%s/file?dir=%s" % (baseurl, dirname(epgdatfile)), timeout=5).read())["files"] if basename(file).startswith("epg.dat")]
			epg_location = files[0] if files else None
			if epg_location:
				print("[ClientModeBox] Copy EPG file from %s" % baseurl)
				try:
					try:
						mkdir("/tmp/epgdat")
					except:
						print("[ClientModeBox] epgdat folder exists in tmp")
					epgdattmp = "/tmp/epgdat"
					epgdatserver = "/tmp/epgdat/epg.dat"
					open("%s/%s" % (epgdattmp, basename(epg_location)), "wb").write(urlopen("%s/file?file=%s" % (baseurl, epg_location), timeout=5).read())
					if "epg.dat" in (epgdatserver):
						move("%s" % epgdatserver, "%s" % (config.misc.epgcache_filename.value))
						eEPGCache.getInstance().load()
						rmtree(epgdattmp)
						AddNotificationWithID("ClientModeBoxEPGImportOK", MessageBox, _("EPG imported successfully from %s") % baseurl, type=MessageBox.TYPE_INFO, timeout=5)
				except Exception as err:
					print("[ClientModeBox] cannot save EPG %s" % err)
		except Exception as err:
			print("[ClientModeBox] cannot save EPG %s" % err)
			return self.downloadEPGFTP(baseurl)

	def downloadParentalControl(self, baseurl):
		print("[ClientModeBox] Reading remote parental control status ...")

		if self.getParentalControlEnabled(baseurl):
			print("[ClientModeBox] Parental control enabled")
			config.ParentalControl.servicepinactive.value = True
			config.ParentalControl.servicepinactive.save()
			print("[ClientModeBox] Reading pin status ...")
			pinstatus = self.getParentalControlPinState(baseurl)
			pin = self.getParentalControlPin(baseurl)
			print("[ClientModeBox] Pin status is setted to " + str(pinstatus))
			config.ParentalControl.servicepinactive.value = pinstatus
			config.ParentalControl.servicepinactive.save()
			config.ParentalControl.servicepin[0].value = pin
			config.ParentalControl.servicepin[0].save()
			print("[ClientModeBox] Reading remote parental control type ...")
			stype = self.getParentalControlType(baseurl)
			print("[ClientModeBox] Parental control type is " + stype)
			config.ParentalControl.type.value = stype
			config.ParentalControl.type.save()
			print("[ClientModeBox] Download parental control services list")
			services = self.downloadParentalControlBouquets(baseurl)
			print("[ClientModeBox] Save parental control services list")
			parentalfile = open("/etc/enigma2/" + stype, "w")
			for service in services:
				parentalfile.write(service['reference'] + "\n")
			parentalfile.close()
			print("[ClientModeBox] Reload parental control")
			from Components.ParentalControl import parentalControl
			parentalControl.open()
		else:
			print("[ClientModeBox] Parental control disabled - do nothing")


class ClientModeBoxAbout(Screen):
	skin = """
			<screen position="100,100" size="560,400">
				<widget name="about"
						position="10,10"
						size="540,340"
						font="Regular;22"
						zPosition="1" />
			</screen>"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self["lab1"] = StaticText(_("OpenVision"))
		self["lab2"] = StaticText(_("Lets define enigma2 once more"))
		self["lab3"] = StaticText(_("Report problems to:"))
		self["lab4"] = StaticText(_("https://openvision.tech"))
		self["lab5"] = StaticText(_("Sources are available at:"))
		self["lab6"] = StaticText(_("https://github.com/OpenVisionE2"))

		self.setTitle(_('Vision Client Mode Box'))

		self['about'] = Label(_("Client Mode Box: If you want to exit Client Mode and have a backup with your original settings. You can restore from blue button on Vision Backup Manager."))
		self["actions"] = ActionMap(["SetupActions"], {
			"cancel": self.keyCancel
		})

	def keyCancel(self):
		self.close()


class ClientModeBoxTimer:
	def __init__(self, session):
		self.session = session
		self.ipboxdownloadtimer = eTimer()
		self.ipboxdownloadtimer.callback.append(self.onIpboxDownloadTimer)

		self.ipboxpolltimer = eTimer()
		self.ipboxpolltimer.timeout.get().append(self.onIpboxPollTimer)

		self.refreshScheduler()

	def onIpboxPollTimer(self):
		self.ipboxpolltimer.stop()
		self.scheduledtime = self.prepareTimer()

	def getTodayScheduledTime(self):
		backupclock = config.ipboxclient.scheduletime.value
		now = localtime(time())
		return int(mktime((now.tm_year, now.tm_mon, now.tm_mday, backupclock[0], backupclock[1], 0, now.tm_wday, now.tm_yday, now.tm_isdst)))

	def prepareTimer(self):
		self.ipboxdownloadtimer.stop()
		scheduled_time = self.getTodayScheduledTime()
		now = int(time())
		if scheduled_time > 0:
			if scheduled_time < now:
				if config.ipboxclient.repeattype.value == "daily":
					scheduled_time += 24 * 3600
					while (int(scheduled_time) - 30) < now:
						scheduled_time += 24 * 3600
				elif config.ipboxclient.repeattype.value == "weekly":
					scheduled_time += 7 * 24 * 3600
					while (int(scheduled_time) - 30) < now:
						scheduled_time += 7 * 24 * 3600
				elif config.ipboxclient.repeattype.value == "monthly":
					scheduled_time += 30 * 24 * 3600
					while (int(scheduled_time) - 30) < now:
						scheduled_time += 30 * 24 * 3600
			next = scheduled_time - now
			self.ipboxdownloadtimer.startLongTimer(next)
		else:
			scheduled_time = -1
		return scheduled_time

	def onIpboxDownloadTimer(self):
		self.ipboxdownloadtimer.stop()
		now = int(time())
		wake = self.getTodayScheduledTime()
		if wake - now < 60:
			downloader = ClientModeBoxDownloader(self.session)
			try:
				downloader.download()
			except Exception as e:
				print(str(e))
		self.scheduledtime = self.prepareTimer()

	def refreshScheduler(self):
		now = int(time())
		if config.ipboxclient.schedule.value:
			if now > 1262304000:
				self.scheduledtime = self.prepareTimer()
			else:
				self.scheduledtime = 0
				self.ipboxpolltimer.start(36000)
		else:
			self.scheduledtime = 0
			self.ipboxpolltimer.stop()


class ClientModeBoxRemoteTimer():
	_timer_list = []
	_processed_timers = []

	on_state_change = []

	last_update_ts = 0

	def __init__(self):
		pass

	@property
	def timer_list(self):
		if self.last_update_ts + 30 < time():
			self.getTimers()
		return self._timer_list

	@timer_list.setter
	def timer_list(self, value):
		self._timer_list = value

	@timer_list.deleter
	def timer_list(self):
		del self._timer_list

	@property
	def processed_timers(self):
		if self.last_update_ts + 30 < time():
			self.getTimers()
		return self._processed_timers

	@processed_timers.setter
	def processed_timers(self, value):
		self._processed_timers = value

	@processed_timers.deleter
	def processed_timers(self):
		del self._processed_timers

	def getTimers(self):
		self._timer_list = []
		self._processed_timers = []

		baseurl = self.getBaseUrl()

		print("[ClientModeBoxRemoteTimer] Get remote timer list")

		try:
			httprequest = urlopen(baseurl + '/web/timerlist')
			xmldoc = minidom.parseString(httprequest.read())
			timers = xmldoc.getElementsByTagName('e2timer')
			for timer in timers:
				serviceref = ServiceReference(getValueFromNode(timer, 'e2servicereference'))
				begin = int(getValueFromNode(timer, 'e2timebegin'))
				end = int(getValueFromNode(timer, 'e2timeend'))
				name = getValueFromNode(timer, 'e2name')
				description = getValueFromNode(timer, 'e2description')
				eit = int(getValueFromNode(timer, 'e2eit'))
				disabled = int(getValueFromNode(timer, 'e2disabled'))
				justplay = int(getValueFromNode(timer, 'e2justplay'))
				afterevent = int(getValueFromNode(timer, 'e2afterevent'))
				repeated = int(getValueFromNode(timer, 'e2repeated'))
				location = getValueFromNode(timer, 'e2location')
				tags = getValueFromNode(timer, 'e2tags').split(" ")

				entry = RecordTimerEntry(serviceref, begin, end, name, description, eit, disabled, justplay, afterevent, dirname=location, tags=tags, descramble=1, record_ecm=0, isAutoTimer=0, always_zap=0)
				entry.repeated = repeated

				entry.orig = RecordTimerEntry(serviceref, begin, end, name, description, eit, disabled, justplay, afterevent, dirname=location, tags=tags, descramble=1, record_ecm=0, isAutoTimer=0, always_zap=0)
				entry.orig.repeated = repeated

				if entry.shouldSkip() or entry.state == TimerEntry.StateEnded or (entry.state == TimerEntry.StateWaiting and entry.disabled):
					insort(self._processed_timers, entry)
				else:
					insort(self._timer_list, entry)
		except Exception as e:
			print("[ClientModeBoxRemoteTimer]", e)

		self.last_update_ts = time()

	def getBaseUrl(self):
		baseurl = "http://"
		if config.ipboxclient.auth.value:
			baseurl += config.ipboxclient.username.value
			baseurl += ":"
			baseurl += config.ipboxclient.password.value
			baseurl += "@"

		baseurl += config.ipboxclient.host.value
		baseurl += ":"
		baseurl += str(config.ipboxclient.port.value)
		return baseurl

	def getNextRecordingTime(self):
		return -1

	def getNextZapTime(self):
		return -1

	def isNextRecordAfterEventActionAuto(self):
		return False

	def isInTimer(self, eventid, begin, duration, service):
		returnValue = None
		type = 0
		time_match = 0
		isAutoTimer = False
		bt = None
		end = begin + duration
		refstr = ":".join(str(service).split(":")[:10]) + ':'
		for x in self._timer_list:
			if x.isAutoTimer == 1:
				isAutoTimer = True
			else:
				isAutoTimer = False
			check = x.service_ref.ref.toString() == refstr
			if check:
				timer_end = x.end
				type_offset = 0
				if x.justplay:
					type_offset = 5
					if (timer_end - x.begin) <= 1:
						timer_end += 60
				if x.always_zap:
					type_offset = 10

				if x.repeated != 0:
					if bt is None:
						bt = localtime(begin)
						et = localtime(end)
						bday = bt.tm_wday
						begin2 = bday * 1440 + bt.tm_hour * 60 + bt.tm_min
						end2 = et.tm_wday * 1440 + et.tm_hour * 60 + et.tm_min
					if x.repeated & (1 << bday):
						xbt = localtime(x.begin)
						xet = localtime(timer_end)
						xbegin = bday * 1440 + xbt.tm_hour * 60 + xbt.tm_min
						xend = bday * 1440 + xet.tm_hour * 60 + xet.tm_min
						if xend < xbegin:
							xend += 1440
						if begin2 < xbegin <= end2:
							if xend < end2: # recording within event
								time_match = (xend - xbegin) * 60
								type = type_offset + 3
							else:           # recording last part of event
								time_match = (end2 - xbegin) * 60
								type = type_offset + 1
						elif xbegin <= begin2 <= xend:
							if xend < end2: # recording first part of event
								time_match = (xend - begin2) * 60
								type = type_offset + 4
							else:           # recording whole event
								time_match = (end2 - begin2) * 60
								type = type_offset + 2
				else:
					if begin < x.begin <= end:
						if timer_end < end: # recording within event
							time_match = timer_end - x.begin
							type = type_offset + 3
						else:           # recording last part of event
							time_match = end - x.begin
							type = type_offset + 1
					elif x.begin <= begin <= timer_end:
						if timer_end < end: # recording first part of event
							time_match = timer_end - begin
							type = type_offset + 4
						else:           # recording whole event
							time_match = end - begin
							type = type_offset + 2
				if time_match:
					if type in (2, 7, 12): # When full recording do not look further
						returnValue = (time_match, [type], isAutoTimer)
						break
					elif returnValue:
						if type not in returnValue[1]:
							returnValue[1].append(type)
					else:
						returnValue = (time_match, [type])

		return returnValue

	def record(self, entry, ignoreTSC=False, dosave=True):
		print("[ClientModeBoxRemoteTimer] Record ", str(entry))

		entry.service_ref = ServiceReference(":".join(str(entry.service_ref).split(":")[:10]))
		args = urlencode({
			'sRef': str(entry.service_ref),
			'begin': str(entry.begin),
			'end': str(entry.end),
			'name': entry.name,
			'disabled': str(1 if entry.disabled else 0),
			'justplay': str(1 if entry.justplay else 0),
			'afterevent': str(entry.afterEvent),
			'dirname': str(entry.dirname),
			'tags': " ".join(entry.tags),
			'repeated': str(entry.repeated),
			'description': entry.description
		})

		baseurl = self.getBaseUrl()

		print("[ClientModeBoxRemoteTimer] Web interface URL: " + baseurl)

		try:
			httprequest = urlopen(baseurl + '/web/timeradd?' + args)
			xmldoc = minidom.parseString(httprequest.read())
			status = xmldoc.getElementsByTagName('e2simplexmlresult')[0]
			success = getValueFromNode(status, 'e2state') == "True"
		except Exception as e:
			print("[ClientModeBoxRemoteTimer]", e)
			return None

		self.getTimers()

		if not success:
			timersanitycheck = TimerSanityCheck(self._timer_list, entry)
			if not timersanitycheck.check():
				print("Timer conflict detected!")
				print(timersanitycheck.getSimulTimerList())
				return timersanitycheck.getSimulTimerList()

		return None

	def timeChanged(self, entry):
		print("[ClientModeBoxRemoteTimer] Timer changed ", str(entry))

		entry.service_ref = ServiceReference(":".join(str(entry.service_ref).split(":")[:10]))
		try:
			args = urlencode({
				'sRef': str(entry.service_ref),
				'begin': str(entry.begin),
				'end': str(entry.end),
				'channelOld': str(entry.orig.service_ref),
				'beginOld': str(entry.orig.begin),
				'endOld': str(entry.orig.end),
				'name': entry.name,
				'disabled': str(1 if entry.disabled else 0),
				'justplay': str(1 if entry.justplay else 0),
				'afterevent': str(entry.afterEvent),
				'dirname': str(entry.dirname),
				'tags': " ".join(entry.tags),
				'repeated': str(entry.repeated),
				'description': entry.description
			})

			baseurl = self.getBaseUrl()
			httprequest = urlopen(baseurl + '/web/timerchange?' + args)
			xmldoc = minidom.parseString(httprequest.read())
			status = xmldoc.getElementsByTagName('e2simplexmlresult')[0]
			success = getValueFromNode(status, 'e2state') == "True"
		except Exception as e:
			print("[ClientModeBoxRemoteTimer]", e)
			return None

		self.getTimers()

		if not success:
			timersanitycheck = TimerSanityCheck(self._timer_list, entry)
			if not timersanitycheck.check():
				print("Timer conflict detected!")
				print(timersanitycheck.getSimulTimerList())
				return timersanitycheck.getSimulTimerList()

		return None

	def removeEntry(self, entry):
		print("[ClientModeBoxRemoteTimer] Timer remove ", str(entry))

		entry.service_ref = ServiceReference(":".join(str(entry.service_ref).split(":")[:10]))
		args = urlencode({
			'sRef': str(entry.service_ref),
			'begin': str(entry.begin),
			'end': str(entry.end)
		})

		baseurl = self.getBaseUrl()
		try:
			httprequest = urlopen(baseurl + '/web/timerdelete?' + args)
			httprequest.read()
		except Exception as e:
			print("[ClientModeBoxRemoteTimer]", e)
			return

		self.getTimers()

	def isRecording(self):
		isRunning = False
		for timer in self.timer_list:
			if timer.isRunning() and not timer.justplay:
				isRunning = True
		return isRunning

	def saveTimer(self):
		pass

	def shutdown(self):
		pass

	def cleanup(self):
		self.processed_timers = [entry for entry in self.processed_timers if entry.disabled]

	def cleanupDaily(self, days):
		limit = time() - (days * 3600 * 24)
		self.processed_timers = [entry for entry in self.processed_timers if (entry.disabled and entry.repeated) or (entry.end and (entry.end > limit))]
