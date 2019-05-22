import numpy as np
from collections import OrderedDict

from rospy_message_converter.message_converter import convert_dictionary_to_ros_message
from scipy.optimize import curve_fit

import symengine_wrappers as sw
from giskardpy.identifier import robot_identifier, world_identifier, js_identifier, constraints_identifier, \
    fk_identifier, closest_point_identifier
from giskardpy.input_system import FrameInput, Point3Input, Vector3Input
from giskardpy.qp_problem_builder import SoftConstraint
from giskardpy.tfwrapper import transform_pose

MAX_WEIGHT = 10
HIGH_WEIGHT = 5
MID_WEIGHT = 1
LOW_WEIGHT = 0.5
ZERO_WEIGHT = 0


class Constraint(object):
    def __init__(self, god_map, **kwargs):
        self.god_map = god_map

    def safe_params_on_god_map(self, params):
        constraints = self.get_god_map().safe_get_data(constraints_identifier)
        constraints[str(self)] = params
        self.get_god_map().safe_set_data(constraints_identifier, constraints)

    def get_constraint(self, **kwargs):
        pass

    def get_identifier(self):
        return constraints_identifier + [str(self)]

    def get_symbol(self, name):
        key = self.get_identifier() + [name]
        return self.god_map.to_symbol(key)

    def get_world_object_pose(self, object_name, link_name):
        pass

    def get_god_map(self):
        """
        :rtype: giskardpy.god_map.GodMap
        """
        return self.god_map

    def get_world(self):
        """
        :rtype: giskardpy.world.World
        """
        return self.get_god_map().safe_get_data(world_identifier)

    def get_robot(self):
        """
        :rtype: giskardpy.symengine_robot.Robot
        """
        return self.get_god_map().safe_get_data(robot_identifier)

    def joint_position_expr(self, joint_name):
        key = js_identifier + [joint_name, u'position']
        return self.god_map.to_symbol(key)

    def __str__(self):
        return self.__class__.__name__

    def get_fk(self, root, tip):
        return self.get_robot().get_fk_expression(root, tip)

    def get_fk_evaluated(self, root, tip):
        return FrameInput(self.get_god_map().to_symbol,
                          translation_prefix=fk_identifier +
                                             [(root, tip),
                                              u'pose',
                                              u'position'],
                          rotation_prefix=fk_identifier +
                                          [(root, tip),
                                           u'pose',
                                           u'orientation']).get_frame()


class JointPosition(Constraint):
    goal = u'goal'
    weight = u'weight'
    gain = u'gain'
    max_speed = u'max_speed'

    def __init__(self, god_map, joint_name, goal, weight=1, gain=10, max_speed=1):
        super(JointPosition, self).__init__(god_map)
        self.joint_name = joint_name
        params = {self.goal: goal,
                  self.weight: weight,
                  self.gain: gain,
                  self.max_speed: max_speed}
        self.safe_params_on_god_map(params)

    def get_constraint(self):
        """
        example:
        name='JointPosition'
        parameter_value_pair='{
            "joint_name": "torso_lift_joint", #required
            "goal_position": 0, #required
            "weight": 1, #optional
            "gain": 10, #optional -- error is multiplied with this value
            "max_speed": 1 #optional -- rad/s or m/s depending on joint; can not go higher than urdf limit
        }'
        :return:
        """

        current_joint = self.joint_position_expr(self.joint_name)

        joint_goal = self.get_symbol(self.goal)
        weight = self.get_symbol(self.weight)
        p_gain = self.get_symbol(self.gain)
        max_speed = self.get_symbol(self.max_speed)

        soft_constraints = OrderedDict()

        if self.get_robot().is_joint_continuous(self.joint_name):
            err = sw.shortest_angular_distance(current_joint, joint_goal)
        else:
            err = joint_goal - current_joint
        capped_err = sw.diffable_max_fast(sw.diffable_min_fast(p_gain * err, max_speed), -max_speed)

        soft_constraints[str(self)] = SoftConstraint(lower=capped_err,
                                                     upper=capped_err,
                                                     weight=weight,
                                                     expression=current_joint)
        return soft_constraints

    def __str__(self):
        return u'{}/{}'.format(self.__class__.__name__, self.joint_name)


class JointPositionList(Constraint):
    def __init__(self, god_map, goal_state, weight=1, gain=10, max_speed=1):
        super(JointPositionList, self).__init__(god_map)
        self.constraints = []
        for i, joint_name in enumerate(goal_state[u'name']):
            goal_position = goal_state[u'position'][i]
            self.constraints.append(JointPosition(god_map, joint_name, goal_position, weight, gain, max_speed))

    def get_constraint(self):
        soft_constraints = OrderedDict()
        for constraint in self.constraints:
            soft_constraints.update(constraint.get_constraint())
        return soft_constraints


class CartesianConstraint(Constraint):
    goal = u'goal'
    weight = u'weight'
    gain = u'gain'
    max_speed = u'max_speed'

    def __init__(self, god_map, root_link, tip_link, goal, weight=HIGH_WEIGHT, gain=3, max_speed=0.1):
        super(CartesianConstraint, self).__init__(god_map)
        self.root = root_link
        self.tip = tip_link
        goal = convert_dictionary_to_ros_message(u'geometry_msgs/PoseStamped', goal)
        goal = transform_pose(self.root, goal)

        # make sure rotation is normalized quaternion
        # TODO make a function out of this
        rotation = np.array([goal.pose.orientation.x,
                             goal.pose.orientation.y,
                             goal.pose.orientation.z,
                             goal.pose.orientation.w])
        normalized_rotation = rotation / np.linalg.norm(rotation)
        goal.pose.orientation.x = normalized_rotation[0]
        goal.pose.orientation.y = normalized_rotation[1]
        goal.pose.orientation.z = normalized_rotation[2]
        goal.pose.orientation.w = normalized_rotation[3]

        params = {self.goal: goal,
                  self.weight: weight,
                  self.gain: gain,
                  self.max_speed: max_speed}
        self.safe_params_on_god_map(params)

    def get_goal_pose(self, name):
        return FrameInput(self.get_god_map().to_symbol,
                          translation_prefix=constraints_identifier +
                                             [str(self),
                                              name,
                                              u'pose',
                                              u'position'],
                          rotation_prefix=constraints_identifier +
                                          [str(self),
                                           name,
                                           u'pose',
                                           u'orientation']).get_frame()

    def __str__(self):
        return u'{}/{}/{}'.format(self.__class__.__name__, self.root, self.tip)


class CartesianPosition(CartesianConstraint):

    def get_constraint(self):
        """
        example:
        name='CartesianPosition'
        parameter_value_pair='{
            "root": "base_footprint", #required
            "tip": "r_gripper_tool_frame", #required
            "goal_position": {"header":
                                {"stamp":
                                    {"secs": 0,
                                    "nsecs": 0},
                                "frame_id": "",
                                "seq": 0},
                            "pose": {"position":
                                        {"y": 0.0,
                                        "x": 0.0,
                                        "z": 0.0},
                                    "orientation": {"y": 0.0,
                                                    "x": 0.0,
                                                    "z": 0.0,
                                                    "w": 0.0}
                                    }
                            }', #required
            "weight": 1, #optional
            "gain": 3, #optional -- error is multiplied with this value
            "max_speed": 0.3 #optional -- rad/s or m/s depending on joint; can not go higher than urdf limit
        }'
        :return:
        """

        goal_position = sw.position_of(self.get_goal_pose(self.goal))
        weight = self.get_symbol(self.weight)
        gain = self.get_symbol(self.gain)
        max_speed = self.get_symbol(self.max_speed)

        current_position = sw.position_of(self.get_fk(self.root, self.tip))

        soft_constraints = OrderedDict()

        trans_error_vector = goal_position - current_position
        trans_error = sw.norm(trans_error_vector)
        trans_scale = sw.diffable_min_fast(trans_error * gain, max_speed)
        trans_control = trans_error_vector / trans_error * trans_scale

        soft_constraints[str(self) + u'x'] = SoftConstraint(lower=trans_control[0],
                                                            upper=trans_control[0],
                                                            weight=weight,
                                                            expression=current_position[0])
        soft_constraints[str(self) + u'y'] = SoftConstraint(lower=trans_control[1],
                                                            upper=trans_control[1],
                                                            weight=weight,
                                                            expression=current_position[1])
        soft_constraints[str(self) + u'z'] = SoftConstraint(lower=trans_control[2],
                                                            upper=trans_control[2],
                                                            weight=weight,
                                                            expression=current_position[2])
        return soft_constraints


class CartesianOrientation(CartesianConstraint):

    def get_constraint(self):
        """
        example:
        name='CartesianPosition'
        parameter_value_pair='{
            "root": "base_footprint", #required
            "tip": "r_gripper_tool_frame", #required
            "goal_position": {"header":
                                {"stamp":
                                    {"secs": 0,
                                    "nsecs": 0},
                                "frame_id": "",
                                "seq": 0},
                            "pose": {"position":
                                        {"y": 0.0,
                                        "x": 0.0,
                                        "z": 0.0},
                                    "orientation": {"y": 0.0,
                                                    "x": 0.0,
                                                    "z": 0.0,
                                                    "w": 0.0}
                                    }
                            }', #required
            "weight": 1, #optional
            "gain": 3, #optional -- error is multiplied with this value
            "max_speed": 0.3 #optional -- rad/s or m/s depending on joint; can not go higher than urdf limit
        }'
        :return:
        """
        goal_rotation = sw.rotation_of(self.get_goal_pose(self.goal))
        weight = self.get_symbol(self.weight)
        gain = self.get_symbol(self.gain)
        max_speed = self.get_symbol(self.max_speed)

        current_rotation = sw.rotation_of(self.get_fk(self.root, self.tip))
        current_evaluated_rotation = sw.rotation_of(self.get_fk_evaluated(self.root, self.tip))

        soft_constraints = OrderedDict()
        axis, angle = sw.diffable_axis_angle_from_matrix((current_rotation.T * goal_rotation))

        capped_angle = sw.diffable_max_fast(sw.diffable_min_fast(gain * angle, max_speed), -max_speed)

        r_rot_control = axis * capped_angle

        hack = sw.rotation_matrix_from_axis_angle([0, 0, 1], 0.0001)

        axis, angle = sw.diffable_axis_angle_from_matrix((current_rotation.T * (current_evaluated_rotation * hack)).T)
        c_aa = (axis * angle)

        soft_constraints[str(self) + u'/0'] = SoftConstraint(lower=r_rot_control[0],
                                                             upper=r_rot_control[0],
                                                             weight=weight,
                                                             expression=c_aa[0])
        soft_constraints[str(self) + u'/1'] = SoftConstraint(lower=r_rot_control[1],
                                                             upper=r_rot_control[1],
                                                             weight=weight,
                                                             expression=c_aa[1])
        soft_constraints[str(self) + u'/2'] = SoftConstraint(lower=r_rot_control[2],
                                                             upper=r_rot_control[2],
                                                             weight=weight,
                                                             expression=c_aa[2])
        return soft_constraints


class CartesianOrientationSlerp(CartesianConstraint):

    def get_constraint(self):
        """
        example:
        name='CartesianPosition'
        parameter_value_pair='{
            "root": "base_footprint", #required
            "tip": "r_gripper_tool_frame", #required
            "goal_position": {"header":
                                {"stamp":
                                    {"secs": 0,
                                    "nsecs": 0},
                                "frame_id": "",
                                "seq": 0},
                            "pose": {"position":
                                        {"y": 0.0,
                                        "x": 0.0,
                                        "z": 0.0},
                                    "orientation": {"y": 0.0,
                                                    "x": 0.0,
                                                    "z": 0.0,
                                                    "w": 0.0}
                                    }
                            }', #required
            "weight": 1, #optional
            "gain": 3, #optional -- error is multiplied with this value
            "max_speed": 0.3 #optional -- rad/s or m/s depending on joint; can not go higher than urdf limit
        }'
        :return:
        """
        goal_rotation = sw.rotation_of(self.get_goal_pose(self.goal))
        weight = self.get_symbol(self.weight)
        gain = self.get_symbol(self.gain)
        max_speed = self.get_symbol(self.max_speed)

        current_rotation = sw.rotation_of(self.get_fk(self.root, self.tip))
        current_evaluated_rotation = sw.rotation_of(self.get_fk_evaluated(self.root, self.tip))

        soft_constraints = OrderedDict()

        axis, angle = sw.diffable_axis_angle_from_matrix((current_rotation.T * goal_rotation))
        angle = sw.diffable_abs(angle)

        capped_angle = sw.diffable_min_fast(max_speed / (gain * angle), 1)

        q1 = sw.quaternion_from_matrix(current_rotation)
        q2 = sw.quaternion_from_matrix(goal_rotation)
        intermediate_goal = sw.diffable_slerp(q1, q2, capped_angle)
        axis, angle = sw.axis_angle_from_quaternion(*sw.quaternion_diff(q1, intermediate_goal))
        r_rot_control = axis * angle

        hack = sw.rotation_matrix_from_axis_angle([0, 0, 1], 0.0001)
        axis, angle = sw.diffable_axis_angle_from_matrix((current_rotation.T * (current_evaluated_rotation * hack)).T)
        c_aa = (axis * angle)

        soft_constraints[str(self) + u'/0'] = SoftConstraint(lower=r_rot_control[0],
                                                             upper=r_rot_control[0],
                                                             weight=weight,
                                                             expression=c_aa[0])
        soft_constraints[str(self) + u'/1'] = SoftConstraint(lower=r_rot_control[1],
                                                             upper=r_rot_control[1],
                                                             weight=weight,
                                                             expression=c_aa[1])
        soft_constraints[str(self) + u'/2'] = SoftConstraint(lower=r_rot_control[2],
                                                             upper=r_rot_control[2],
                                                             weight=weight,
                                                             expression=c_aa[2])
        return soft_constraints


class LinkToAnyAvoidance(Constraint):
    repel_speed = u'repel_speed'
    max_weight_distance = u'max_weight_distance'
    low_weight_distance = u'low_weight_distance'
    zero_weight_distance = u'zero_weight_distance'
    A = u'A'
    B = u'B'
    C = u'C'

    def __init__(self, god_map, link_name, repel_speed=0.1, max_weight_distance=0.0, low_weight_distance=0.02,
                 zero_weight_distance=0.05):
        super(LinkToAnyAvoidance, self).__init__(god_map)
        self.link_name = link_name
        x = np.array([max_weight_distance, low_weight_distance, zero_weight_distance])
        y = np.array([MAX_WEIGHT, LOW_WEIGHT, ZERO_WEIGHT])
        (A, B, C), _ = curve_fit(lambda t, a, b, c: a / (t + c) + b, x, y)
        params = {self.repel_speed: repel_speed,
                  self.max_weight_distance: max_weight_distance,
                  self.low_weight_distance: low_weight_distance,
                  self.zero_weight_distance: zero_weight_distance,
                  self.A: A,
                  self.B: B,
                  self.C: C}
        self.safe_params_on_god_map(params)

    def get_distance_to_closest_object(self, link_name):
        return self.get_god_map().to_symbol(closest_point_identifier + [link_name, u'min_dist'])

    def get_contact_normal_on_b(self, link_name):
        return Vector3Input(self.god_map.to_symbol,
                            prefix=closest_point_identifier + [link_name, u'contact_normal']).get_expression()

    def get_closest_point_on_a(self, link_name):
        return Point3Input(self.god_map.to_symbol,
                           prefix=closest_point_identifier + [link_name, u'position_on_a']).get_expression()

    def get_closest_point_on_b(self, link_name):
        return Point3Input(self.god_map.to_symbol,
                           prefix=closest_point_identifier + [link_name, u'position_on_b']).get_expression()

    def get_constraint(self):
        current_pose = self.get_fk(self.get_robot().get_root(), self.link_name)
        current_pose_eval = self.get_fk_evaluated(self.get_robot().get_root(), self.link_name)
        point_on_link = self.get_closest_point_on_a(self.link_name)
        other_point = self.get_closest_point_on_b(self.link_name)
        contact_normal = self.get_contact_normal_on_b(self.link_name)
        repel_speed = self.get_symbol(self.repel_speed)
        max_weight_distance = self.get_symbol(self.max_weight_distance)
        low_weight_distance = self.get_symbol(self.low_weight_distance)
        zero_weight_distance = self.get_symbol(self.zero_weight_distance)
        A = self.get_symbol(self.A)
        B = self.get_symbol(self.B)
        C = self.get_symbol(self.C)

        soft_constraints = OrderedDict()

        controllable_point = current_pose * sw.inverse_frame(current_pose_eval) * point_on_link

        dist = (contact_normal.T * (controllable_point - other_point))[0]

        weight_f = sw.Piecewise([MAX_WEIGHT, dist <= max_weight_distance],
                                [ZERO_WEIGHT, dist > zero_weight_distance],
                                [A / (dist + C) + B, True])

        soft_constraints[str(self)] = SoftConstraint(lower=repel_speed,
                                                     upper=repel_speed,
                                                     weight=weight_f,
                                                     expression=dist)
        return soft_constraints

    def __str__(self):
        return u'{}/{}'.format(self.__class__.__name__, self.link_name)


class CollisionAvoidance(Constraint):

    def __init__(self, god_map, **kwargs):
        super(CollisionAvoidance, self).__init__(god_map, **kwargs)

    def get_constraint(self, **kwargs):
        super(CollisionAvoidance, self).get_constraint(**kwargs)


class Grasp(CartesianConstraint):

    def __init__(self, god_map, root, tip, goal, weight=HIGH_WEIGHT, gain=3, max_speed=0.1):
        super(Grasp, self).__init__(god_map, root, tip, goal, weight, gain, max_speed)

    def __str__(self):
        return super(Grasp, self).__str__()


def add_debug_constraint(d, key, expr):
    """
    If you want to see an arbitrary evaluated expression in the matrix use this.
    These softconstraints will not influence anything.
    :param d: a dict where the softcontraint will be added to
    :type: dict
    :param key: a name to identify the debug soft contraint
    :type key: str
    :type expr: sw.Symbol
    """
    d[key] = SoftConstraint(lower=expr,
                            upper=expr,
                            weight=0,
                            expression=1)