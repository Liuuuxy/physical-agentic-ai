cmake_minimum_required(VERSION 3.8)
project(sar_msgs)

find_package(ament_cmake REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "srv/Takeoff.srv"
  "srv/Land.srv"
  "srv/FlyTo.srv"
  "srv/SearchArea.srv"
  "srv/NavigateTo.srv"
  "srv/Stop.srv"
  "srv/PerceptionQuery.srv"
)

ament_package()
