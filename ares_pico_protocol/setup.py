from setuptools import setup


package_name = 'ares_pico_protocol'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='robocon',
    maintainer_email='robocon@example.com',
    description='USB CDC protocol client for the ARES RP2040 LED driver.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'ares_pico_cli = ares_pico_protocol.cli:main',
            'ares_pico_protocol_node = ares_pico_protocol.node:main',
        ],
    },
)
