import setuptools

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setuptools.setup(
    name="yinshield", 
    version="0.0.1",
    author="Tingcai Chen", 
    author_email="revdd@vip.qq.com",
    description="A zero-config, local-first privacy layer for AI APIs with semantic-preserving de-identification.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/serein-213/yin-shield", 
    project_urls={
        "Bug Tracker": "https://github.com/serein-213/yin-shield/issues",
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "Topic :: Security",
    ],
    package_dir={"": "."},
    packages=setuptools.find_packages(),
    python_requires=">=3.7",
    install_requires=[
        "requests", 
        "faker",    
    ],

    extras_require={
        "ai": [
            "onnxruntime", 
            "numpy",
        ],
    },
    keywords="privacy, llm, openai, deepseek, pii, security, ai-safety",
)
