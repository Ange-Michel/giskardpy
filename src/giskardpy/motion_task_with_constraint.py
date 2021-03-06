#!/usr/bin/env python

import rospy
import sys
import tf
# from control_msgs.msg import GripperCommandAction
from giskardpy.python_interface import GiskardWrapper
from giskardpy.utils_constraints import Utils
from geometry_msgs.msg import PoseStamped, Point, Quaternion
from iai_naive_kinematics_sim.srv import SetJointState, SetJointStateRequest, SetJointStateResponse  # comment this line
from sensor_msgs.msg import JointState
import numpy as np
from tf.transformations import quaternion_about_axis
import tf2_ros
import tf2_geometry_msgs
from giskardpy.qp_problem_builder import SoftConstraint
from collections import OrderedDict
from geometry_msgs.msg import Vector3Stamped, Vector3
from rospy_message_converter.message_converter import convert_dictionary_to_ros_message
from giskardpy import constraints as cnst
from giskardpy import god_map as gm
from giskardpy import tfwrapper as tf_wrapper
from giskardpy import symbolic_wrapper as w
from urdf_parser_py.urdf import URDF
import math
import yaml
from giskardpy import utils_constraints as uc
from giskardpy.tfwrapper import lookup_pose, pose_to_kdl, np_to_kdl, kdl_to_pose
import actionlib
from control_msgs.msg import GripperCommandAction, GripperCommandGoal
from pr2_controllers_msgs.msg import Pr2GripperCommandAction, Pr2GripperCommandActionGoal, Pr2GripperCommandGoal



class MotionTaskWithConstraint:
    """
    the class helps to select the necessary constraints, to select the gripper and to check the orientation of the base.
    """
    # list of Gripper
    _list_grippers = []
    # Torso of robot
    _torso = ""
    # Reference frame to basefootprint
    _origin = ""
    # goal frame
    _goal = ""

    def __init__(self):
        print("MotionTaskWithConstraint is initialized !")
        self._giskard = GiskardWrapper()

        rospy.logout("- Set pose kitchen")
        kitchen_pose = tf_wrapper.lookup_pose("map", "iai_kitchen/world")
        kitchen_pose.header.frame_id = "map"
        # setup kitchen
        rospy.logout("- Get urdf")
        self.urdf = rospy.get_param("kitchen_description")
        self.parsed_urdf = URDF.from_xml_string(self.urdf)
        self.config_file = None

        rospy.logout("- clear urdf and add kitchen urdf")
        self._giskard.clear_world()
        self._giskard.add_urdf(name="kitchen", urdf=self.urdf, pose=kitchen_pose, js_topic="kitchen/cram_joint_states")

    def set_gripper_for_real_roboter(self):
        # setup gripper as actionlib
        self.rgripper = actionlib.SimpleActionClient('r_gripper/gripper_command', GripperCommandAction)
        self.lgripper = actionlib.SimpleActionClient('l_gripper/gripper_command', GripperCommandAction)
        self.rgripper.wait_for_server()
        self.lgripper.wait_for_server()

    def r_action_gripper(self, value=0):
        goal = Pr2GripperCommandGoal() #GripperCommandGoal()
        goal.command.position = value
        goal.command.max_effort = 40
        self.rgripper.send_goal_and_wait(goal)

    def l_action_gripper(self, value=0):
        goal = Pr2GripperCommandGoal() #GripperCommandGoal()
        goal.command.position = value
        goal.command.max_effort = 40
        self.lgripper.send_goal_and_wait(goal)

    def execute_open_translational_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self.r_action_gripper(0.012)
        self.l_action_gripper(0.012)
        self._giskard.set_json_goal("OpenCloseDrawerConstraint", goal_name=goal, body_name=body, action=action)
        self._giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                             joint_states={joint: joint_value})

    def execute_close_translational_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_json_goal("OpenCloseDrawerConstraint", goal_name=goal, body_name=body, action=action)
        self._giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                             joint_states={joint: joint_value})

    def execute_open_circular_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self.r_action_gripper(0.012)
        self.l_action_gripper(0.012)
        self._giskard.set_json_goal("OpenCloseDoorConstraint", goal_name=goal, body_name=body, action=action)
        self._giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                             joint_states={joint: joint_value})

    def execute_close_circular_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_json_goal("OpenCloseDoorConstraint", goal_name=goal, body_name=body, action=action)
        self._giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                             joint_states={joint: joint_value})

    def execute_open_rotational_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self.r_action_gripper(0.012)
        self.l_action_gripper(0.012)
        self._giskard.set_json_goal("TurnRotaryKnobConstraint", goal_name=goal, body_name=body, action=action)
        self._giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                             joint_states={joint: joint_value})

    def execute_close_rotational_motion_on_real_robot(self, goal, body, action, joint, joint_value):
        self.r_action_gripper(0.08)
        self.l_action_gripper(0.08)
        self._giskard.set_json_goal("MoveToPoseConstraint", goal_name=goal, body_name=body)
        self._giskard.allow_all_collisions()
        self._giskard.plan_and_execute()
        self._giskard.set_json_goal("TurnRotaryKnobConstraint", goal_name=goal, body_name=body, action=action)
        self.giskard.allow_all_collisions()
        # self.giskard.avoid_all_collisions()
        self.giskard.plan_and_execute()
        self._giskard.set_object_joint_state(object_name='kitchen',
                                            joint_states={joint: joint_value})

    def setup_orientation_basis(self, basis_frame="odom_combined", torso="torso_lift_link",
                                list_grippers=["r_gripper_tool_frame", "l_gripper_tool_frame"]):
        """
        This method set the parameter for the orientations verification of the basis
        :param basis_frame: origin frame to the basis
        :type: str
        :param torso: torso of robot
        :type: str
        :param list_grippers: List of gripper
        :type: array of str
        :return:
        """
        self._list_grippers = list_grippers
        self._torso = torso
        self._origin = basis_frame

    def set_goal(self, goal=""):
        """
        set the goal in relation to which the base is to be oriented
        :param goal: goal
        :type: str
        :return:
        """
        self._goal = goal

    def update_basis_orientation(self):
        """
        This function update the orientation of the basis and get the next Gripper in short distance from goal
        :return:
        """
        x, y, r = self.get_current_base_position()
        rospy.logout("The basis is at position :")
        rospy.logout(x)
        rospy.logout(y)
        rospy.logout(r)
        # get pose torso
        pose_torso = tf_wrapper.lookup_pose(self._origin, self._torso)
        # get pose goal
        pose_goal = tf_wrapper.lookup_pose(self._origin, self._goal)
        # get list of pose of gripper
        list_pose_gripper = [tf_wrapper.lookup_pose(self._origin, p) for p in self._list_grippers]
        # get angle to G
        angle = [float(w.get_angle_casadi(self.get_x_y(pose_torso), self.get_x_y(pose_goal), self.get_x_y(p)))
                 for p in list_pose_gripper]
        # max angle G to goal
        max_angle = np.amax(angle)
        rospy.logout("Max angle is :")
        rospy.logout(max_angle)
        # update old and new orientation
        max_angle = r + max_angle
        rospy.logout("Max angle + r is :")
        rospy.logout(max_angle)
        # get selected Gripper
        gripper = np.where(np.array(angle) == np.amax(angle))
        rospy.logout("Farther away Gripper:")
        rospy.logout(gripper[0][0])
        # convert angle in axis
        q = w.quaternion_from_axis_angle([0, 0, 1], max_angle)
        # update basis orientation
        #self.set_cart_goal_for_basis(x, y, 0, q)

    #@staticmethod
    def get_x_y(self, pose):
        return [pose.pose.position.x, pose.pose.position.y, 0]

    def get_current_base_position(self):
        """
        the method check the current pose of base_footprint to odom and get it
        :return: x, y, rotation
        """
        basis = tf_wrapper.lookup_pose(self._origin, "base_footprint")
        t, r = [basis.pose.position.x, basis.pose.position.y, basis.pose.position.z], \
               [basis.pose.orientation.x, basis.pose.orientation.y, basis.pose.orientation.z,
                basis.pose.orientation.w]  # self.get_msg_translation_and_rotation(self._basis, "map")
        return self.base_position(t, r)

    def base_position(self, translation, rotation):
        """
        the method take the translation and rotation from tf_ros and calculate the rotation in euler
        :param translation: vector
        :param rotation: quaternion (from tf_ros)
        :return: vector[x, y, rotation], current base position
        """
        euler = tf.transformations.euler_from_quaternion(rotation)
        return translation[0], translation[1], euler[2]

    def set_cart_goal_for_basis(self, x, y, z, q):
        """
        this function send goal to the basis of robot
        :param x: position on x axis
        :type: float
        :param y: position on y axis
        :type: float
        :param z: position on z axis
        :type: float
        :param q: quaternion orientation
        :type: array float
        :return:
        """
        # take base_footprint
        poseStamp = lookup_pose(self._origin, "base_footprint")
        poseStamp.header.frame_id = self._origin
        # set goal pose
        poseStamp.pose.position.x = x
        poseStamp.pose.position.y = y
        poseStamp.pose.position.z = z
        poseStamp.pose.orientation.x = q[0]
        poseStamp.pose.orientation.y = q[1]
        poseStamp.pose.orientation.z = q[2]
        poseStamp.pose.orientation.w = q[3]
        self._giskard.set_cart_goal(self._origin, "base_footprint", poseStamp)
        self._giskard.avoid_all_collisions()
        self._giskard.plan_and_execute()

    def reset_kitchen(self, list_joints):
        for j in list_joints:
            self._giskard.set_object_joint_state(object_name='kitchen',
                                                 joint_states={j: 0.0})


if __name__ == '__main__':
    rospy.init_node('do_test_constraint')
    list_joint = [
        "sink_area_trash_drawer_main_joint",
        "sink_area_left_upper_drawer_main_joint",
        "sink_area_left_middle_drawer_main_joint",
        "sink_area_left_bottom_drawer_main_joint",
        "sink_area_dish_washer_main_joint",
        "sink_area_dish_washer_door_joint",
        "oven_area_oven_door_joint",
        "oven_area_oven_knob_stove_1_joint",
        "oven_area_oven_knob_stove_2_joint",
        "oven_area_oven_knob_stove_3_joint",
        "oven_area_oven_knob_stove_4_joint",
        "oven_area_oven_knob_oven_joint",
        "oven_area_area_middle_upper_drawer_main_joint",
        "oven_area_area_middle_lower_drawer_main_joint",
        "oven_area_area_left_drawer_main_joint",
        "oven_area_area_right_drawer_main_joint",
        "kitchen_island_left_upper_drawer_main_joint",
        "kitchen_island_left_lower_drawer_main_joint",
        "kitchen_island_middle_upper_drawer_main_joint",
        "kitchen_island_middle_lower_drawer_main_joint",
        "kitchen_island_right_upper_drawer_main_joint",
        "kitchen_island_right_lower_drawer_main_joint",
        "fridge_area_lower_drawer_main_joint",
        "iai_fridge_door_joint"
    ]
    rospy.logout("START SOME MOVE as Test")
    mc = MotionTaskWithConstraint()
    mc.set_gripper_for_simulator()
    # fridge door
    #mc.execute_open_circular_motion_on_real_robot('iai_kitchen/iai_fridge_door_handle', 'r_gripper_tool_frame', 0.5,
                                                 #'iai_fridge_door_joint', 0.758)
    #mc.execute_close_circular_motion_on_real_robot('iai_kitchen/iai_fridge_door_handle', 'r_gripper_tool_frame', -0.5,
                                                  #'iai_fridge_door_joint', 0.0)

    #mc.reset_kitchen(list_joint)

    # kitchen_island_left_upper_drawer
    #mc.execute_open_translational_motion_on_real_robot("iai_kitchen/kitchen_island_left_upper_drawer_handle",
                                                      #"r_gripper_tool_frame", 1,
                                                      #"kitchen_island_left_upper_drawer_main_joint", 0.48)
    #mc.execute_close_translational_motion_on_real_robot("iai_kitchen/kitchen_island_left_upper_drawer_handle",
                                                       #"r_gripper_tool_frame", -1,
                                                       #"kitchen_island_left_upper_drawer_main_joint", 0.0)
    #mc.reset_kitchen(list_joint)

    # iai_kitchen/oven_area_oven_door_handle
    #mc.execute_open_circular_motion_on_real_robot('iai_kitchen/oven_area_oven_door_handle', 'l_gripper_tool_frame', -1,
                                                 #'oven_area_oven_door_joint', 1.57)
    #mc.execute_close_circular_motion_on_real_robot('iai_kitchen/oven_area_oven_door_handle', 'l_gripper_tool_frame', 1,
                                                  #'oven_area_oven_door_joint', 0.0)
    #mc.reset_kitchen(list_joint)

    # iai_kitchen/sink_area_dish_washer_door_handle
    mc.execute_open_circular_motion_on_real_robot('iai_kitchen/sink_area_dish_washer_door_handle',
                                                 'r_gripper_tool_frame',
                                                 -0.5, 'sink_area_dish_washer_door_joint', 0.758)
    mc.execute_close_circular_motion_on_real_robot('iai_kitchen/sink_area_dish_washer_door_handle',
                                                  'r_gripper_tool_frame',
                                                  0.5, 'sink_area_dish_washer_door_joint', 0)
    #mc.reset_kitchen(list_joint)

    # iai_kitchen/sink_area_left_middle_drawer_handle
    #mc.execute_open_translational_motion_on_real_robot('iai_kitchen/sink_area_left_middle_drawer_handle',
                                                      #'r_gripper_tool_frame', -1,
                                                      #'sink_area_left_middle_drawer_main_joint', 0.48)
    #mc.execute_close_translational_motion_on_real_robot('iai_kitchen/sink_area_left_middle_drawer_handle',
                                                       #'r_gripper_tool_frame', 1,
                                                       #'sink_area_left_middle_drawer_main_joint', 0.0)
    #mc.reset_kitchen(list_joint)

    # iai_kitchen/oven_area_oven_knob_stove_4
    #mc.execute_rotational_motion_on_real_robot('iai_kitchen/oven_area_oven_knob_stove_4', 'l_gripper_tool_frame', -1,
                                              #"oven_area_oven_knob_stove_4_joint", 1.57)

    # set_cart_goal_test()
    rospy.spin()
