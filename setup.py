from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="bcda-client",
    version="1.0.0",
    packages=find_packages(),
    install_requires=requirements,
    author="Carlos Pacheco",
    author_email="admin@data-nt.com",
    description="A Python client for the BCDA (Beneficiary Claims Data API)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/pachecocarlos27/bcda-client",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Healthcare Industry",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",
) 