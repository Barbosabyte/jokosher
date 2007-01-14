#
#	THIS FILE IS PART OF THE JOKOSHER PROJECT AND LICENSED UNDER THE GPL. SEE
#	THE 'COPYING' FILE FOR DETAILS
#
#	ProjectManager.py
#
#	Contains various helper classes for the Project class as well as
#	all of the loading and saving to and from project files.
#
#=========================================================================

import urlparse, os, gzip, shutil, gst
import Globals, Utils, UndoSystem
import Project, Instrument, Event
import xml.dom.minidom as xml

""" (Singleton) Unique reference to the currently active Project object. """
GlobalProjectObject = None

def CreateNewProject(projecturi, name, author):
	"""
	Creates a new Project.

	Parameters:
		projecturi -- the filesystem location for the new Project.
						Currently, only file:// URIs are considered valid.
		name --	the name of the Project.
		author - the name of the Project's author.
		
	Returns:
		the newly created Project object.
	"""
	if name == "" or author == "" or projecturi == "":
		raise CreateProjectError(4)

	(scheme, domain,folder, params, query, fragment) = urlparse.urlparse(projecturi, "file")

	if scheme != "file":
		# raise "The URI scheme used is invalid." message
		raise CreateProjectError(5)

	filename = name + ".jokosher"
	projectdir = os.path.join(folder, name)

	try:
		project = Project.Project()
	except gst.PluginNotFoundError, e:
		Globals.debug("Missing Gstreamer plugin:", e)
		raise CreateProjectError(6, str(e))
	except Exception, e:
		Globals.debug("Could not initialize project object:", e)
		raise CreateProjectError(1)

	project.name = name
	project.author = author
	project.projectfile = os.path.join(projectdir, filename)

	if os.path.exists(projectdir):
		raise CreateProjectError(2)
	else: 
		audio_dir = os.path.join(projectdir, "audio")
		try:
			os.mkdir(projectdir)
			os.mkdir(audio_dir)
		except:
			raise CreateProjectError(3)

	project.SaveProjectFile(project.projectfile)

	return project

#_____________________________________________________________________

def ValidateProject(project):
	"""
	Checks that the Project is valid - i.e. that the files and 
	images it references can be found.
	
	Parameters:
		project -- The project to validate.
	
	Returns:
		True -- the Project is valid.
		False -- the Project contains non-existant files and/or images.
	"""
	unknownfiles=[]
	unknownimages=[]

	for instr in project.instruments:
		for event in instr.events:
			if (event.file!=None) and (not os.path.exists(event.file)) and (not event.file in unknownfiles):
				unknownfiles.append(event.file)
	if len(unknownfiles) > 0 or len(unknownimages) > 0:
		raise InvalidProjectError(unknownfiles,unknownimages)

	return True
	
#_____________________________________________________________________

def CloseProject():
	"""
	Close the current project.
	"""
	global GlobalProjectObject
	GlobalProjectObject.CloseProject()
	GlobalProjectObject = None
	
#_____________________________________________________________________

def LoadProjectFile(uri):
	"""
	Loads a Project from a saved file on disk.

	Parameters:
		uri -- the filesystem location of the Project file to load. 
				Currently only file:// URIs are considered valid.
				
	Returns:
		the loaded Project object.
	"""
	
	(scheme, domain, projectfile, params, query, fragment) = urlparse.urlparse(uri, "file")
	if scheme != "file":
		# raise "The URI scheme used is invalid." message
		raise OpenProjectError(1, scheme)

	Globals.debug("Attempting to open:", projectfile)

	if not os.path.exists(projectfile):
		raise OpenProjectError(4, projectfile)

	try:
		gzipfile = gzip.GzipFile(projectfile, "r")
		doc = xml.parse(gzipfile)
	except Exception, e:
		Globals.debug(e.__class__, e)
		# raise "This file doesn't unzip" message
		raise OpenProjectError(2, projectfile)
	
	project = Project.Project()
	project.projectfile = projectfile
	
	#only open projects with the proper version number
	version = doc.firstChild.getAttribute("version")
	if JOKOSHER_VERSION_FUNCTIONS.has_key(version):
		loaderClass = JOKOSHER_VERSION_FUNCTIONS[version]
		Globals.debug("Loading project file version", version)
		loaderClass(project, doc)
		if version != Globals.VERSION:
			#if we're loading an old version copy the project so that it is not overwritten when the user clicks save
			withoutExt = os.path.splitext(projectfile)[0]
			shutil.copy(projectfile, "%s.%s.jokosher" % (withoutExt, version))
		return project
	else:
		# raise a "this project was created in an incompatible version of Jokosher" message
		raise OpenProjectError(3, version)

#=========================================================================

class _LoadZPOFile:
	def __init__(self, project, xmlDoc):
		"""
		Loads a project from a Jokosher 0.1 (Zero Point One) Project file into
		the given Project object using the given XML document.
		
		Parameters:
			project -- the Project instance to apply loaded properties to.
			xmlDoc -- the XML file document to read data from.
		"""
		params = xmlDoc.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(project, params)
		
		for instr in xmlDoc.getElementsByTagName("Instrument"):
			try:
				id = int(instr.getAttribute("id"))
			except ValueError:
				id = None
			i = Instrument.Instrument(project, None, None, None, id)
			self.LoadInstrument(i, instr)
			project.instruments.append(i)
			if i.isSolo:
				project.soloInstrCount += 1
	
	#_____________________________________________________________________
	
	def LoadInstrument(self, instr, xmlNode):
		"""
		Loads instrument properties from a Jokosher 0.1 XML node
		and saves them to the given Instrument instance.
		
		Parameters:
			instr -- the Instrument instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		Utils.LoadParametersFromXML(instr, params)
		#work around because in >0.2 instr.effects is a list not a string.
		instr.effects = []
		
		for ev in xmlNode.getElementsByTagName("Event"):
			try:
				id = int(ev.getAttribute("id"))
			except ValueError:
				id = None
			e = Event.Event(instr, None, id)
			self.LoadEvent(e, ev)
			instr.events.append(e)
		
		pixbufFilename = os.path.basename(instr.pixbufPath)
		instr.instrType = os.path.splitext(pixbufFilename)[0]
			
		for i in Globals.getCachedInstruments():
			if instr.instrType == i[1]:
				instr.pixbuf = i[2]
				break
		if not instr.pixbuf:
			Globals.debug("Error, could not load image:", instr.instrType)
			
		#initialize the actuallyIsMuted variable
		instr.OnMute()
		
	#_____________________________________________________________________
	
	def LoadEvent(self, event, xmlNode):
		"""
		Loads event properties from a Jokosher 0.1 XML node
		and saves then to the given Event instance.
		
		Parameters:
			event -- the Event instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		Utils.LoadParametersFromXML(event, params)
		
		try:
			xmlPoints = xmlNode.getElementsByTagName("FadePoints")[0]
		except IndexError:
			Globals.debug("Missing FadePoints in Event XML")
		else:
			for n in xmlPoints.childNodes:
				if n.nodeType == xml.Node.ELEMENT_NODE:
					pos = float(n.getAttribute("position"))
					value = float(n.getAttribute("fade"))
					event._Event__fadePointsDict[pos] = value
		
		try:	
			levelsXML = xmlNode.getElementsByTagName("Levels")[0]
		except IndexError:
			Globals.debug("No event levels in project file")
			event.GenerateWaveform()
		else: 
			if levelsXML.nodeType == xml.Node.ELEMENT_NODE:
				value = str(levelsXML.getAttribute("value"))
				event.levels = map(float, value.split(","))
		
		if event.isLoading:
			event.GenerateWaveform()

		event._Event__UpdateAudioFadePoints()
		event.CreateFilesource()
	
	#_____________________________________________________________________

#=========================================================================

class _LoadZPTFile:
	def __init__(self, project, xmlDoc):
		"""
		Loads a Jokosher version 0.2 (Zero Point Nine) Project file into
		the given Project object using the given XML document.
		
		Parameters:
			project -- the Project instance to apply loaded properties to.
			xmlDoc -- the XML file document to read data from.
		"""
		self.project = project
		self.xmlDoc = xmlDoc
		
		params = self.xmlDoc.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(self.project, params)
		
		# Hack to set the transport mode
		self.project.transport.SetMode(self.project.transportMode)
		
		for instrElement in self.xmlDoc.getElementsByTagName("Instrument"):
			try:
				id = int(instrElement.getAttribute("id"))
			except ValueError:
				id = None
			instr = Instrument.Instrument(self.project, None, None, None, id)
			self.LoadInstrument(instr, instrElement)
			self.project.instruments.append(instr)
			if instr.isSolo:
				self.project.soloInstrCount += 1
	
	#_____________________________________________________________________
	
	def LoadInstrument(self, instr, xmlNode):
		"""
		Restores an Instrument from version 0.2 XML representation.
		
		Parameters:
			instr -- the Instrument instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(instr, params)
		
		#figure out the instrument's path based on the location of the projectfile
		instr.path = os.path.join(os.path.dirname(self.project.projectfile), "audio")
		
		globaleffect = xmlNode.getElementsByTagName("GlobalEffect")
		
		for effect in globaleffect:
			elementname = str(effect.getAttribute("element"))
			Globals.debug("Loading effect:", elementname)
			gstElement = instr.AddEffect(elementname)
			
			propsdict = Utils.LoadDictionaryFromXML(effect)
			for key, value in propsdict.iteritems():
				gstElement.set_property(key, value)		
			
		for ev in xmlNode.getElementsByTagName("Event"):
			try:
				id = int(ev.getAttribute("id"))
			except ValueError:
				id = None
			event = Event.Event(instr, None, id)
			self.LoadEvent(event, ev)
			instr.events.append(event)
		
		#load image from file based on unique type
		for instrTuple in Globals.getCachedInstruments():
			if instr.instrType == instrTuple[1]:
				instr.pixbuf = instrTuple[2]
				break
		if not instr.pixbuf:
			Globals.debug("Error, could not load image:", instr.instrType)
		
		# load pan level
		instr.panElement.set_property("panorama", instr.pan)
		#check if instrument is muted and setup accordingly
		instr.OnMute()
		
	#_____________________________________________________________________
		
	def LoadEvent(self, event, xmlNode):
		"""
		Restores an Event from its version 0.2 XML representation.
		
		Parameters:
			event -- the Event instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(event, params)
		
		if not os.path.isabs(event.file):
			# If there is a relative path for event.file, assume it is in the audio dir
			event.file = os.path.join(event.instrument.path, event.file)
		
		try:
			xmlPoints = xmlNode.getElementsByTagName("FadePoints")[0]
		except IndexError:
			Globals.debug("Missing FadePoints in Event XML")
		else:
			event._Event__fadePointsDict = Utils.LoadDictionaryFromXML(xmlPoints)
		
		try:	
			levelsXML = xmlNode.getElementsByTagName("Levels")[0]
		except IndexError:
			Globals.debug("No event levels in project file")
			event.GenerateWaveform()
		else: 
			if levelsXML.nodeType == xml.Node.ELEMENT_NODE:
				value = str(levelsXML.getAttribute("value"))
				event.levels = map(float, value.split(","))

		if event.isLoading or event.isRecording:
			event.GenerateWaveform()

		event._Event__UpdateAudioFadePoints()
		event.CreateFilesource()
	
	#_____________________________________________________________________
#=========================================================================

class _LoadZPNFile:
	def __init__(self, project, xmlDoc):
		"""
		Loads a Jokosher version 0.9 (Zero Point Nine) Project file into
		the given Project object using the given XML document.
		
		Parameters:
			project -- the Project instance to apply loaded properties to.
			xmlDoc -- the XML file document to read data from.
		"""
		self.project = project
		self.xmlDoc = xmlDoc
		
		params = self.xmlDoc.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(self.project, params)
		
		# Hack to set the transport mode
		self.project.transport.SetMode(self.project.transportMode)
		
		undoRedo = (("Undo", self.project._Project__savedUndoStack),
				("Redo", self.project._Project__redoStack))
		for tagName, stack in undoRedo:
			try:
				undo = self.xmlDoc.getElementsByTagName(tagName)[0]
			except IndexError:
				Globals.debug("No saved %s in project file" % tagName)
			else:
				for actionNode in undo.childNodes:
					if actionNode.nodeName == "Action":
						# Don't add to the undo stack because the it will go to the wrong stack
						action = UndoSystem.AtomicUndoAction(addToStack=False)
						self.LoadUndoAction(action, actionNode)
						stack.append(action)
		
		for instrElement in self.xmlDoc.getElementsByTagName("Instrument"):
			try:
				id = int(instrElement.getAttribute("id"))
			except ValueError:
				id = None
			instr = Instrument.Instrument(self.project, None, None, None, id)
			self.LoadInstrument(instr, instrElement)
			self.project.instruments.append(instr)
			if instr.isSolo:
				self.project.soloInstrCount += 1
		
		for instrElement in self.xmlDoc.getElementsByTagName("DeadInstrument"):
			try:
				id = int(instrElement.getAttribute("id"))
			except ValueError:
				id = None
			instr = Instrument.Instrument(self.project, None, None, None, id)
			self.LoadInstrument(instr, instrElement)
			self.project.graveyard.append(instr)
			instr.RemoveAndUnlinkPlaybackbin()
	
	#_____________________________________________________________________
	
	def LoadInstrument(self, instr, xmlNode):
		"""
		Restores an Instrument from version 0.9 XML representation.
		
		Parameters:
			instr -- the Instrument instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(instr, params)
		
		#figure out the instrument's path based on the location of the projectfile
		instr.path = os.path.join(os.path.dirname(self.project.projectfile), "audio")
		
		globaleffect = xmlNode.getElementsByTagName("GlobalEffect")
		
		for effect in globaleffect:
			elementname = str(effect.getAttribute("element"))
			Globals.debug("Loading effect:", elementname)
			gstElement = instr.AddEffect(elementname)
			
			propsdict = Utils.LoadDictionaryFromXML(effect)
			for key, value in propsdict.iteritems():
				gstElement.set_property(key, value)		
			
		for ev in xmlNode.getElementsByTagName("Event"):
			try:
				id = int(ev.getAttribute("id"))
			except ValueError:
				id = None
			event = Event.Event(instr, None, id)
			self.LoadEvent(event, ev)
			instr.events.append(event)
	
		for ev in xmlNode.getElementsByTagName("DeadEvent"):
			try:
				id = int(ev.getAttribute("id"))
			except ValueError:
				id = None
			event = Event.Event(instr, None, id)
			self.LoadEvent(event, ev)
			instr.graveyard.append(event)
			#remove it from the composition so it doesnt play
			instr.composition.remove(event.filesrc)
		
		#load image from file based on unique type
		for instrTuple in Globals.getCachedInstruments():
			if instr.instrType == instrTuple[1]:
				instr.pixbuf = instrTuple[2]
				break
		if not instr.pixbuf:
			Globals.debug("Error, could not load image:", instr.instrType)
		
		# load pan level
		instr.panElement.set_property("panorama", instr.pan)
		#check if instrument is muted and setup accordingly
		instr.OnMute()
		
	#_____________________________________________________________________
		
	def LoadEvent(self, event, xmlNode):
		"""
		Restores an Event from its version 0.9 XML representation.
		
		Parameters:
			event -- the Event instance to apply loaded properties to.
			xmlNode -- the XML node to retreive data from.
		"""
		params = xmlNode.getElementsByTagName("Parameters")[0]
		
		Utils.LoadParametersFromXML(event, params)
		
		if not os.path.isabs(event.file):
			# If there is a relative path for event.file, assume it is in the audio dir
			event.file = os.path.join(event.instrument.path, event.file)
		
		try:
			xmlPoints = xmlNode.getElementsByTagName("FadePoints")[0]
		except IndexError:
			Globals.debug("Missing FadePoints in Event XML")
		else:
			event._Event__fadePointsDict = Utils.LoadDictionaryFromXML(xmlPoints)
		
		try:	
			levelsXML = xmlNode.getElementsByTagName("Levels")[0]
		except IndexError:
			Globals.debug("No event levels in project file")
			event.GenerateWaveform()
		else: 
			if levelsXML.nodeType == xml.Node.ELEMENT_NODE:
				value = str(levelsXML.getAttribute("value"))
				event.levels = map(float, value.split(","))

		if event.isLoading or event.isRecording:
			event.GenerateWaveform()

		event._Event__UpdateAudioFadePoints()
		event.CreateFilesource()
	
	#_____________________________________________________________________
	
	def LoadUndoAction(self, undoAction, xmlNode):
		"""
		Loads an AtomicUndoAction from an XML node.
		
		Parameters:
			undoAction -- the AtomicUndoAction instance to save the loaded commands to.
			node -- XML node from which the AtomicUndoAction is loaded.
					Should be an "<Action>" node.
			
		Returns:
			the loaded AtomicUndoAction object.
		"""
		for cmdNode in xmlNode.childNodes:
			if cmdNode.nodeName == "Command":
				objectString = str(cmdNode.getAttribute("object"))
				functionString = str(cmdNode.getAttribute("function"))
				paramList = Utils.LoadListFromXML(cmdNode)
				
				undoAction.AddUndoCommand(objectString, functionString, paramList)
		
	#_____________________________________________________________________
#=========================================================================

class OpenProjectError(EnvironmentError):
	"""
	This class will get created when a opening a Project fails.
	It's used for handling errors.
	"""
	
	#_____________________________________________________________________
	
	def __init__(self, errno, info = None):
		"""
		Creates a new instance of OpenProjectError.
		
		Parameters:
			errno -- number indicating the type of error:
					1 = invalid uri passed for the Project file.
					2 = unable to unzip the Project.
					3 = Project created by a different version of Jokosher.
					4 = Project file doesn't exist.
			info -- version of Jokosher that created the Project.
					Will be present only along with error #3.
		"""
		EnvironmentError.__init__(self)
		self.info = info
		self.errno = errno
	
	#_____________________________________________________________________
	
#=========================================================================

class CreateProjectError(Exception):
	"""
	This class will get created when creating a Project fails.
	It's used for handling errors.
	"""
	
	#_____________________________________________________________________
	
	def __init__(self, errno, message=None):
		"""
		Creates a new instance of CreateProjectError.
		
		Parameters:
			errno -- number indicating the type of error:
					1 = unable to create a Project object.
					2 = path for Project file already exists.
					3 = unable to create file. (Invalid permissions, read-only, or the disk is full).
					4 = invalid path, name or author.
					5 = invalid uri passed for the Project file.
					6 = unable to load a particular gstreamer plugin (message will be the plugin's name)
			message -- a string with more specific information about the error
		"""
		Exception.__init__(self)
		self.errno = errno
		self.message = message
		
	#_____________________________________________________________________

#=========================================================================

class AudioInputsError(Exception):
	"""
	This class will get created when there are problems with the soundcard inputs.
	It's used for handling errors.
	"""
	
	#_____________________________________________________________________
	
	def __init__(self, errno):
		"""
		Creates a new instance of AudioInputsError.
		
		Parameters:
			errno -- number indicating the type of error:
					1 = no recording channels found.
					2 = sound card is not capable of multiple simultaneous inputs.
					3 = channel splitting element not found.
		"""
		Exception.__init__(self)
		self.errno = errno
		
	#_____________________________________________________________________

#=========================================================================

class InvalidProjectError(Exception):
	"""
	This class will get created when there's an invalid Project.
	It's used for handling errors.
	"""
	
	#_____________________________________________________________________
	
	def __init__(self, missingfiles, missingimages):
		"""
		Creates a new instance of InvalidProjectError.
		
		Parameters:
			missingfiles -- filenames of the missing files.
			missingimages -- filenames of the missing images.
		"""
		Exception.__init__(self)
		self.files=missingfiles
		self.images=missingimages
		
	#_____________________________________________________________________

#=========================================================================

JOKOSHER_VERSION_FUNCTIONS = {"0.1" : _LoadZPOFile, "0.2" : _LoadZPTFile, "0.9" : _LoadZPNFile}

#=========================================================================