# -*- coding: utf-8 -*-
from . import _
from Components.ActionMap import ActionMap
from Components.ChoiceList import ChoiceList, ChoiceEntryComponent
from Components.config import config
from Components.Label import Label
from Components.SystemInfo import BoxInfo
from Components.Sources.StaticText import StaticText
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Tools.BoundFunction import boundFunction
from Tools.MultiBoot import getCurrentImage, getCurrentImageMode, getImageList, emptySlot


class MultiBoot(Screen):

	skin = """
	<screen name="MultiBoot" position="center,center" size="750,900" flags="wfNoBorder" backgroundColor="transparent">
		<eLabel name="b" position="0,0" size="750,700" backgroundColor="#00ffffff" zPosition="-2" />
		<eLabel name="a" position="1,1" size="748,698" backgroundColor="#00000000" zPosition="-1" />
		<widget source="Title" render="Label" position="60,10" foregroundColor="#00ffffff" size="480,50" horizontalAlignment="left" font="Regular; 28" backgroundColor="#00000000" />
		<eLabel name="line" position="1,60" size="748,1" backgroundColor="#00ffffff" zPosition="1" />
		<eLabel name="line2" position="1,250" size="748,4" backgroundColor="#00ffffff" zPosition="1" />
		<widget name="config" position="2,280" size="730,380" horizontalAlignment="center" font="Regular; 22" backgroundColor="#00000000" foregroundColor="#00e5b243" />
		<widget source="labe14" render="Label" position="2,80" size="730,30" horizontalAlignment="center" font="Regular; 22" backgroundColor="#00000000" foregroundColor="#00ffffff" />
		<widget source="labe15" render="Label" position="2,130" size="730,60" horizontalAlignment="center" font="Regular; 22" backgroundColor="#00000000" foregroundColor="#00ffffff" />
		<widget source="key_red" render="Label" position="30,200" size="150,30" noWrap="1" zPosition="1" verticalAlignment="center" font="Regular; 20" horizontalAlignment="left" backgroundColor="#00000000" foregroundColor="#00ffffff" />
		<widget source="key_green" render="Label" position="200,200" size="150,30" noWrap="1" zPosition="1" verticalAlignment="center" font="Regular; 20" horizontalAlignment="left" backgroundColor="#00000000" foregroundColor="#00ffffff" />
		<eLabel position="20,200" size="6,40" backgroundColor="#00e61700" /> <!-- Should be a pixmap -->
		<eLabel position="190,200" size="6,40" backgroundColor="#0061e500" /> <!-- Should be a pixmap -->
	</screen>
	"""

	def __init__(self, session):
		Screen.__init__(self, session)
		self.setTitle(_("Vision MultiBoot Image Manager"))
		self["key_red"] = StaticText(_("Cancel"))
		self["labe14"] = StaticText(_("Use the cursor keys to select an installed image and then Erase button."))
		self["labe15"] = StaticText(_("Note: slot list does not show current image or empty slots."))
		self["key_green"] = StaticText(_("Erase"))
		self["key_yellow"] = StaticText("")
		self["config"] = ChoiceList(list=[ChoiceEntryComponent('', ((_("Retrieving image slots - Please wait...")), "Queued"))])
		imagedict = []
		self.imageList = None
		self.startit()

		self["actions"] = ActionMap(["OkCancelActions", "ColorActions", "DirectionActions", "KeyboardInputActions", "MenuActions"], {
			"red": boundFunction(self.close, None),
			"green": self.erase,
			"yellow": boundFunction(self.close, None),
			"ok": self.erase,
			"cancel": boundFunction(self.close, None),
			"up": self.keyUp,
			"down": self.keyDown,
			"left": self.keyLeft,
			"right": self.keyRight,
			"upRepeated": self.keyUp,
			"downRepeated": self.keyDown,
			"leftRepeated": self.keyLeft,
			"rightRepeated": self.keyRight,
			"menu": boundFunction(self.close, True),
		}, -1)

	def startit(self):
		self.imageList = getImageList(self.ImageList)

	def ImageList(self, imagedict):
		list = []
		mode = getCurrentImageMode() or 0
		currentimageslot = getCurrentImage()
		for x in sorted(imagedict.keys()):
			if imagedict[x]["imagename"] != _("Empty slot") and x != currentimageslot:
				list.append(ChoiceEntryComponent('', ((_("slot%s - %s ")) % (x, imagedict[x]['imagename']), x)))
		self["config"].setList(list)

	def erase(self):
		self.currentSelected = self["config"].l.getCurrentSelection()
		if self.currentSelected != None:
			if self.currentSelected[0][1] != "Queued":
				if BoxInfo.getItem("HasRootSubdir"):
					message = _("Removal of this slot will not show in %s GUI.  Are you sure you want to delete image slot?" % (self.currentSelected[0][1]))
					ybox = self.session.openWithCallback(self.doErase, MessageBox, message, MessageBox.TYPE_YESNO, default=True)
					ybox.setTitle(_("Remove confirmation"))
				else:
					message = _("Are you sure you want to delete image slot %s ?" % self.currentSelected[0][1])
					ybox = self.session.openWithCallback(self.doErase, MessageBox, message, MessageBox.TYPE_YESNO, default=True)
					ybox.setTitle(_("Remove confirmation"))

	def doErase(self, answer):
		if answer is True:
			sloterase = emptySlot(self.currentSelected[0][1], self.startit)

	def selectionChanged(self):
		pass

	def keyLeft(self):
		self["config"].instance.moveSelection(self["config"].instance.moveUp)
		self.selectionChanged()

	def keyRight(self):
		self["config"].instance.moveSelection(self["config"].instance.moveDown)
		self.selectionChanged()

	def keyUp(self):
		self["config"].instance.moveSelection(self["config"].instance.moveUp)
		self.selectionChanged()

	def keyDown(self):
		self["config"].instance.moveSelection(self["config"].instance.moveDown)
		self.selectionChanged()
