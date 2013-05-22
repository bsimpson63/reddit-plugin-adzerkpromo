#!/usr/bin/env python
from setuptools import setup, find_packages

setup(name='reddit_adzerkpromo',
    description='reddit adzerk sponsored headlines',
    version='0.1',
    author='Brian Simpson',
    author_email='brian@reddit.com',
    license='BSD',
    packages=find_packages(),
    install_requires=[
        'r2',
        'adzerk',
        'requests',
    ],
    entry_points={
        'r2.plugin':
            ['adzerkpromo = reddit_adzerkpromo:AdzerkPromo']
    },
    include_package_data=True,
    zip_safe=False,
)
