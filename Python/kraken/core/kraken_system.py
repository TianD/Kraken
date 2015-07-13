"""KrakenSystem - objects.kraken_core module.

Classes:
KrakenSystem - Class for constructing the Fabric Engine Core client.

"""

import os
import json
import imp
import importlib
import kraken
from kraken.core.profiler import Profiler
import FabricEngine.Core


class KrakenSystem(object):
    """The KrakenSystem is a singleton object used to provide an interface with
    the FabricEngine Core and RTVal system."""

    __instance = None

    def __init__(self):
        """Initializes the Kraken System object."""

        super(KrakenSystem, self).__init__()

        self.client = None
        self.typeDescs = None
        self.registeredTypes = None
        self.loadedExtensions = []

        self.registeredComponents = {}


    def loadCoreClient(self):
        """Loads the Fabric Engine Core Client

        Return:
        None

        """

        if self.client == None:
            Profiler.getInstance().push("loadCoreClient")

            try:
                imp.find_module('cmds')
                host = 'Maya'
            except ImportError:
                try:
                    imp.find_module('sipyutils')
                    host = 'Softimage'
                except ImportError:
                    host = 'Python'

            if host == "Python":
                self.client = FabricEngine.Core.createClient()

            elif host == "Maya":
                contextID = cmds.fabricSplice('getClientContextID')
                if contextID == '':
                    cmds.fabricSplice('constructClient')
                    contextID = cmds.fabricSplice('getClientContextID')

                # Pull out the Splice client.
                self.client = FabricEngine.Core.createClient({"contextID": contextID})

            elif host == "Softimage":
                from win32com.client.dynamic import Dispatch
                si = Dispatch("XSI.Application").Application
                contextID = si.fabricSplice('getClientContextID')
                if contextID == '':
                    si.fabricSplice('constructClient')
                    contextID = si.fabricSplice('getClientContextID')

                # Pull out the Splice client.
                self.client = FabricEngine.Core.createClient({"contextID": contextID})

            self.loadExtension('Math')

            Profiler.getInstance().pop()


    def getCoreClient(self):
        """Returns the Fabric Engine Core Client owned by the KrakenSystem

        Return:
        The Fabric Engine Core Client

        """

        if self.client is None:
            self.loadCoreClient()

        return self.client


    def loadExtension(self, extension):
        """Loads the given extension and updates the registeredTypes cache.

        Arguments:
        extension -- string, The name of the extension to load.

        Return:
        None

        """

        if extension not in self.loadedExtensions:
            Profiler.getInstance().push("loadExtension:" + extension)
            self.client.loadExtension(extension)
            self.registeredTypes = self.client.RT.types
            self.typeDescs = self.client.RT.getRegisteredTypes()
            # Cache the loaded extension so that we aviod refreshing the typeDescs cache(costly)
            self.loadedExtensions.append(extension)
            Profiler.getInstance().pop()


    def constructRTVal(self, dataType, defaultValue=None):
        """Constructs a new RTVal using the given name and optional devault value.

        Arguments:
        dataType -- string, The name of the data type to construct.
        defaultValue -- value, The default value to use to initialize the RTVal

        Return:
        The constructed RTval.

        """

        self.loadCoreClient()
        klType = getattr(self.registeredTypes, dataType)

        if defaultValue is not None:
            if hasattr(defaultValue, '_rtval'):
                return defaultValue._rtval

            typeDesc = self.typeDescs[dataType]
            if 'members' in typeDesc:
                try:
                    value = klType.create()
                except:
                    value = klType()
                for i in range(0, len(typeDesc['members'])):
                    memberName = typeDesc['members'][i]['name']
                    memberType = typeDesc['members'][i]['type']
                    if memberName in defaultValue:
                        setattr(value, memberName, self.constructRTVal(memberType, getattr(defaultValue, memberName)))
                return value

            else:
                return klType(defaultValue)
        else:
            try:
                return klType.create()
            except:
                try:
                    return klType()
                except Exception as e:
                    raise Exception("Error constructing RTVal:" + dataType)


    def rtVal(self, dataType, defaultValue=None):
        """Constructs a new RTVal using the given name and optional devault value.

        Arguments:
        dataType -- string, The name of the data type to construct.
        defaultValue -- value, The default value to use to initialize the RTVal

        Return:
        The constructed RTval.

        """

        return self.constructRTVal(dataType, defaultValue)


    def isRTVal(self, value):
        """Returns true if the given value is an RTVal.

        Arguments:
        value -- value, value to test.

        Return:
        True if successful.

        """

        return str(type(value)) == "<type 'PyRTValObject'>"


    def getRTValTypeName(self, rtval):
        """Returns the name of the type, handling extracting the name from KL RTVals.

        Arguments:
        rtval -- rtval, the rtval to extract the name from.

        Return:
        True if successful.

        """

        if ks.isRTVal(rtval):
            return json.loads(rtval.type("Type").jsonDesc("String"))['name']
        else:
            return "None"


    def registerComponent(self, componentClass):
        """Registers a component Python class with the KrakenSystem so ti can be built by the rig builder.

        Arguments:
        componentClass -- string, the Python class of the component

        Return:
        None

        """

        componentModulePath = componentClass.__module__ + "." + componentClass.__name__
        if componentModulePath in self.registeredComponents:
            # we allow reregistring of components because as a componet's class is edited
            # it will be re-imported by python(in Maya), and the classes reregistered.
            pass

        self.registeredComponents[componentModulePath] = componentClass


    def getComponentClass(self, className):
        """Returns the registered Python component class with the given name

        Arguments:
        className -- string, The name of the Python component class

        Return:
        The Python component class

        """

        if className not in self.registeredComponents:
            raise Exception("Component with that class not registered:" + className)

        return self.registeredComponents[className]


    def getComponentClassNames(self):
        """Returns the names of the registered Python component classes

        Return:
        The array of component class names.

        """

        return self.registeredComponents.keys()


    def loadComponentModules(self, iniFilePath=None):
        """Loads all the component modules specified in the 'KRAKEN_COMPONENT_PATHS' environment variable. 
        If the environment variable is not set, then the kraken_examples are loaded.

        Return:
        None

        """

        pathsVar = os.getenv('KRAKEN_COMPONENT_PATHS')

        def __importDirRecursive(path, parentModulePath=''):
            for root, dirs, files in os.walk(path, True, None):

                # parse all the files of given path and import python modules
                for sfile in files:
                    if sfile.endswith(".py"):
                        if sfile == "__init__.py":
                            module = parentModulePath
                        else:
                            module = parentModulePath+"."+sfile[:-3]

                        try:
                            importlib.import_module(module)
                        except ImportError, e:
                            print "Error loading Kraken components from environment variable:" + str(pathsVar)
                            print "The paths must point to the root of importable python modules."
                            for arg in e.args:
                                print arg
                        except Exception, e:
                            for arg in e.args:
                                print arg

                # Now reload sub modules
                for dirName in dirs:
                    __importDirRecursive(os.path.join(path,dirName), parentModulePath+"."+dirName)

        if pathsVar is None:
            # find the kraken examples module in the same folder as the kraken module. 
            pathsVar = os.path.join(os.path.dirname(os.path.dirname(kraken.__file__)), 'kraken_examples')

        pathsList = pathsVar.split(';')

        for path in pathsList:
            __importDirRecursive(path, os.path.basename(path))


    @classmethod
    def getInstance(cls):
        """This class method returns the singleton instance for the KrakenSystem

        Return:
        The singleton instance.

        """

        if cls.__instance is None:
            cls.__instance = KrakenSystem()

        return cls.__instance



ks = KrakenSystem.getInstance()