from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Define requirements directly in setup.py
requirements = [
    "requests>=2.25.0",
    "pandas>=1.0.0",
    "pyarrow>=3.0.0",
    "tqdm",
    "pytest>=6.0.0",
    "pytest-benchmark>=3.4.1",  # For performance testing
    "psutil>=5.8.0",  # For memory monitoring
    "pyarrow>=3.0.0",  # For Parquet support
    "pandas>=1.0.0"    # For data processing
]

setup(
    name="bcda-client-datant",
    version="0.2.0",
    packages=find_packages(exclude=["tests*"]),
    install_requires=requirements,
    author="Carlos Pacheco",
    author_email="admin@data-nt.com",
    description="A Python client for the BCDA (Beneficiary Claims Data API)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pachecocarlos27/bcda-client",
    project_urls={
        "Bug Tracker": "https://github.com/pachecocarlos27/bcda-client/issues",
        "Documentation": "https://github.com/pachecocarlos27/bcda-client#readme",
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Medical Science Apps.",
    ],
    python_requires=">=3.6",
    keywords="healthcare, bcda, cms, medicare, api-client",
    include_package_data=True,
    zip_safe=False,
) 