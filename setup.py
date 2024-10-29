import os
from setuptools import setup, find_packages

HERE = os.path.abspath(os.path.dirname(__file__))


# Get the long description from the README file.
with open(os.path.join(HERE, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="experimental_protocol_fetcher",
    author="Blue Brain Project, EPFL",
    use_scm_version={
        "relative_to": __file__,
        "write_to": "experimental_protocol_fetcher/version.py",
        "write_to_template": "__version__ = '{version}'\n",
    },
    description="Tools for retrieving experimental protocols used in generating data.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    keywords="data",
    packages=find_packages(),
    python_requires=">=3.7,<3.10",
    include_package_data=True,
    setup_requires=[
        "setuptools_scm",
    ],
    install_requires=[
        "nexusforge",
        "requests"
    ],
    extras_require={
        "dev": [
            "tox==4.13.0"
        ]
    },
    classifiers=[
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering",
        "Programming Language :: Python :: 3 :: Only",
        "Natural Language :: English",
    ]
)
