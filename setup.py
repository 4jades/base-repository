from setuptools import setup, find_packages

INSTALL_REQUIRES = [
    "pydantic>=1.7.4",
    "sqlalchemy>=1.4",
    "typing-extensions>=4.6.0",
]

EXTRAS_REQUIRE = {
    ':python_version >= "3.13"': [
        "pydantic>=2.8.0,<3.0.0"
    ]
}

setup(
    name="base-repository",
    version="1.0.1",
    description="A repository library that wraps SQLAlchemy and provides built-in CRUD and a query DSL.", 
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author="jjade",
    author_email="jjades1205@gmail.com",
    url='https://github.com/4jades/base-repository',
    packages=find_packages(exclude=["tests", "tests.*"]), 
    python_requires='>=3.10,<3.14',
    install_requires=INSTALL_REQUIRES,
    extras_require=EXTRAS_REQUIRE,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
)