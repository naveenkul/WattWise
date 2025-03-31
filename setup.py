from setuptools import setup, find_packages

setup(
    name="wattwise",
    version="0.1.3",
    author="Naveen",
    author_email="hey@naveen.ing",
    description="A CLI tool for monitoring power usage by devices plugged into smart plugs",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/naveenkul/wattwise",
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        "typer>=0.7.0",
        "rich>=12.0.0",
        "python-kasa>=0.5.0",
        "requests>=2.28.0",
        "pyyaml>=6.0",
        "asyncio>=3.4.3",
    ],
    entry_points="""
        [console_scripts]
        wattwise=wattwise.cli:app
    """,
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Utilities",
    ],
    python_requires=">=3.8",
)
