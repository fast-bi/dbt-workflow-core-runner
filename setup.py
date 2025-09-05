import os
from setuptools import setup, find_packages

# Get the version from the environment variable or default to '0.0.0'
version = os.getenv('CI_COMMIT_TAG', '0.0.0')

setup(
    name="fast_bi_dbt_runner",
    version=version,  # Set the version here
    author="Fast.Bi",
    author_email="support@fast.bi",
    maintainer="Fast.Bi",
    maintainer_email="administrator@fast.bi",
    description="Private Python library who provides managing for set up DBT DAGs.",
    url="https://gitlab.fast.bi/infrastructure/bi-platform-pypi-packages/fast_bi_dbt_runner",
    packages=find_packages(),
    include_package_data=True,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.8',
    setup_requires=['setuptools'],
)
