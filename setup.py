"""
Workflow Engine - 配置驱动的任务编排框架

安装方法:
    pip install -e .
或
    python setup.py install
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="yawe",
    version="1.0.0",
    author="Tom James",
    author_email="tomjamescn@gmail.com",
    description="YAWE - Yet Another Workflow Engine: 一个轻量级、配置驱动的工作流任务编排框架",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/tomjamescn/yawe",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Application Frameworks",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
    ],
    python_requires=">=3.6",
    install_requires=[
        "PyYAML>=5.1",
        "Jinja2>=2.11",
        "requests>=2.25",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0",
            "pytest-cov>=2.10",
            "black>=21.0",
            "flake8>=3.8",
        ],
    },
    entry_points={
        "console_scripts": [
            "workflow-run=workflow_engine.cli:main",
        ],
    },
)
