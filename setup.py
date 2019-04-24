import os
from setuptools import find_packages, setup

with open(os.path.join(os.path.dirname(__file__), "README.md")) as readme:
    README = readme.read()

# allow setup.py to be run from any path
os.chdir(os.path.normpath(os.path.join(os.path.abspath(__file__), os.pardir)))

setup(
    name="nuntius",
    version="0.3.17",
    packages=find_packages(exclude=["tests", "tests.*"]),
    include_package_data=True,
    license="GPLv3",
    description="A model agnostic Django newsletter app integrating Mosaico.",
    long_description=README,
    url="https://github.com/lafranceinsoumise/nuntius",
    author="Jill Royer",
    author_email="perso@guilro.com",
    install_requires=("celery", "pillow", "html2text"),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Web Environment",
        "Framework :: Django",
        "Framework :: Django :: 2.0",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.6",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Internet :: WWW/HTTP :: Dynamic Content",
        "Topic :: Communications :: Email",
    ],
)
