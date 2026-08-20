from setuptools import find_packages, setup

package_name = 'sar_robot_control'

setup(
    name=package_name,
    version='0.1.0',
    packages=find_packages(exclude=['test']),
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Anonymous',
    maintainer_email='anonymous@example.invalid',
    description='Control nodes for the IRIS drone (MAVROS) and TurtleBot3 rover',
    license='Apache-2.0',
    entry_points={
        'console_scripts': [
            'drone_controller_node = sar_robot_control.drone_controller_node:main',
            'rover_controller_node = sar_robot_control.rover_controller_node:main',
        ],
    },
)
