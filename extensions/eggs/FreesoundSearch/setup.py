from setuptools import setup
import sys, os
from shutil import copy

version = "0.2"
setup(name="FreesoundSearch",
	  version=version,
	  author='Stuart Langridge, David Corrales',
	  author_email='sil-launchpad@kryogenix.org',
	  description='Freesound browsing extension.',
	  long_description="Searches the Freesound library of freely licenceable and useable sound clips.",
	  license='GNU GPL',
	  platforms='linux',
	  packages=["FreesoundSearch"],
	  package_dir={"FreesoundSearch":"src"},
	  package_data={"":["FreesoundSearch.glade", "freesound.py"]},
	  entry_points="""
		[jokosher.extensions]
		extension = FreesoundSearch:FreesoundSearch
		"""
)

# copy egg file to the deployment directory in the svn structure
copy("dist/FreesoundSearch-%s-py%d.%d.egg" % (version, sys.version_info[0], sys.version_info[1]),
	 "../../") 
