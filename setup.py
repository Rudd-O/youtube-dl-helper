#!/usr/bin/python3

from setuptools import setup
import os

dir = os.path.dirname(__file__)
path_to_main_file = os.path.join(dir, "src/youtubedlhelper/__init__.py")
path_to_readme = os.path.join(dir, "README.md")
for line in open(path_to_main_file):
	if line.startswith('__version__'):
		version = line.split()[-1].strip("'").strip('"')
		break
else:
	raise ValueError('"__version__" not found in "src/youtubedlhelper/__init__.py"')
readme = open(path_to_readme).read(-1)

classifiers = [
'Development Status :: 5 - Production/Stable',
'Environment :: X11 Applications :: GTK',
'Intended Audience :: End Users/Desktop',
'License :: OSI Approved :: GNU General Public License (GPL)',
'Operating System :: POSIX :: Linux',
'Programming Language :: Python :: 3 :: Only',
'Programming Language :: Python :: 3.6',
'Topic :: Communications :: File Sharing',
'Topic :: Utilities',
]

setup(
	name = 'youtube-dl-helper',
	version=version,
	description = 'A tool to automate YouTube downloads via drag and drop',
	long_description = readme,
	author='Manuel Amador (Rudd-O)',
	author_email='rudd-o@rudd-o.com',
	license="GPL",
	url = 'http://github.com/Rudd-O/youtube-dl-helper',
	package_dir=dict([
		("youtubedlhelper", "src/youtubedlhelper"),
	]),
	classifiers = classifiers,
	packages = ["youtubedlhelper"],
	data_files = [
		('share/youtube-dl-helper', ['youtube-dl-helper/youtube-dl-helper.glade']),
		('share/pixmaps', ['pixmaps/youtube-dl-helper.png']),
		("share/applications", ["youtube-dl-helper.desktop"]),
	],
	scripts = ['bin/youtube-dl-helper'],
	keywords = "YouTube download",
	zip_safe=False,
)
