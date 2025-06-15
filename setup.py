from setuptools import setup, find_packages

setup(
    name="quant-libs",  # Package name
    version="0.0.1",    # Version number
    packages=find_packages("indicators"),  # Automatically find packages
    install_requires=[  # List dependencies
        #"requests>=2.25.1",
        #"numpy>=1.19.2",
    ],
    extras_require={
        "indicators": []
    },
    author="reshnah",
    author_email="reshnah1@gmail.com",
    description="Quant libraries",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    url="https://github.com/reshnah/quant-libs",  # GitHub repo URL
    classifiers=[  # Metadata for PyPI
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.6",  # Minimum Python version
)