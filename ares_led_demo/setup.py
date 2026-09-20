from glob import glob
from setuptools import setup


package_name = 'ares_led_demo'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml', 'README.md']),
        ('share/' + package_name + '/launch', glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    tests_require=['pytest'],
    zip_safe=True,
    maintainer='robocon',
    maintainer_email='robocon@example.com',
    description='Concise topic demo for the ARES LED protocol node.',
    license='MIT',
    entry_points={
        'console_scripts': [
            'demo = ares_led_demo.demo:main',
        ],
    },
)
