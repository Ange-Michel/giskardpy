import json

import rospy
from actionlib import SimpleActionClient
from genpy import Message
from geometry_msgs.msg import PoseStamped, Point, Quaternion, Vector3Stamped
from giskard_msgs.msg import MoveAction, MoveGoal, WorldBody, CollisionEntry, MoveResult, Constraint, \
    MoveCmd, JointConstraint, CartesianConstraint
from giskard_msgs.srv import UpdateWorld, UpdateWorldRequest, UpdateWorldResponse, GetObjectInfo, GetObjectNames,\
    UpdateRvizMarkers, GetAttachedObjects
from rospy_message_converter.message_converter import convert_ros_message_to_dictionary
from sensor_msgs.msg import JointState
from shape_msgs.msg import SolidPrimitive
from visualization_msgs.msg import MarkerArray

from giskardpy.urdf_object import URDFObject
from giskardpy.utils import dict_to_joint_states, make_world_body_box, make_world_body_cylinder
from giskardpy import logging


class GiskardWrapper(object):
    def __init__(self, giskard_topic=u'giskardpy/command', ns=u'giskard'):
        if giskard_topic is not None:
            self.client = SimpleActionClient(giskard_topic, MoveAction)
            self.update_world = rospy.ServiceProxy(u'{}/update_world'.format(ns), UpdateWorld)
            self.get_object_names = rospy.ServiceProxy(u'{}/get_object_names'.format(ns), GetObjectNames)
            self.get_object_info = rospy.ServiceProxy(u'{}/get_object_info'.format(ns), GetObjectInfo)
            self.update_rviz_markers = rospy.ServiceProxy(u'{}/update_rviz_markers'.format(ns), UpdateRvizMarkers)
            self.get_attached_objects = rospy.ServiceProxy(u'{}/get_attached_objects'.format(ns), GetAttachedObjects)
            self.marker_pub = rospy.Publisher(u'visualization_marker_array', MarkerArray, queue_size=10)
            rospy.wait_for_service(u'{}/update_world'.format(ns))
            self.client.wait_for_server()
        self.tip_to_root = {}
        self.robot_urdf = URDFObject(rospy.get_param(u'robot_description'))
        self.collisions = []
        self.clear_cmds()
        self.object_js_topics = {}
        rospy.sleep(.3)

    def get_robot_name(self):
        return self.robot_urdf.get_name()

    def get_root(self):
        return self.robot_urdf.get_root()

    def set_cart_goal(self, root, tip, pose_stamped, trans_max_velocity=None, rot_max_velocity=None):
        """
        :param tip:
        :type tip: str
        :param pose_stamped:
        :type pose_stamped: PoseStamped
        """
        self.set_translation_goal(root, tip, pose_stamped, max_velocity=trans_max_velocity)
        self.set_rotation_goal(root, tip, pose_stamped, max_velocity=rot_max_velocity)

    def set_translation_goal(self, root, tip, pose_stamped, weight=None, max_velocity=None):
        """
        :param tip:
        :type tip: str
        :param pose_stamped:
        :type pose_stamped: PoseStamped
        """
        if not max_velocity and not weight:
            constraint = CartesianConstraint()
            constraint.type = CartesianConstraint.TRANSLATION_3D
            constraint.root_link = str(root)
            constraint.tip_link = str(tip)
            constraint.goal = pose_stamped
            self.cmd_seq[-1].cartesian_constraints.append(constraint)
        else:
            constraint = Constraint()
            constraint.type = u'CartesianPosition'
            params = {}
            params[u'root_link'] = root
            params[u'tip_link'] = tip
            params[u'goal'] = convert_ros_message_to_dictionary(pose_stamped)
            if max_velocity:
                params[u'max_velocity'] = max_velocity
            if weight:
                params[u'weight'] = weight
            constraint.parameter_value_pair = json.dumps(params)
            self.cmd_seq[-1].constraints.append(constraint)

    def set_rotation_goal(self, root, tip, pose_stamped, weight=None, max_velocity=None):
        """
        :param tip:
        :type tip: str
        :param pose_stamped:
        :type pose_stamped: PoseStamped
        """
        if not max_velocity and not weight:
            constraint = CartesianConstraint()
            constraint.type = CartesianConstraint.ROTATION_3D
            constraint.root_link = str(root)
            constraint.tip_link = str(tip)
            constraint.goal = pose_stamped
            self.cmd_seq[-1].cartesian_constraints.append(constraint)
        else:
            constraint = Constraint()
            constraint.type = u'CartesianOrientationSlerp'
            params = {}
            params[u'root_link'] = root
            params[u'tip_link'] = tip
            params[u'goal'] = convert_ros_message_to_dictionary(pose_stamped)
            if max_velocity:
                params[u'max_velocity'] = max_velocity
            if weight:
                params[u'weight'] = weight
            constraint.parameter_value_pair = json.dumps(params)
            self.cmd_seq[-1].constraints.append(constraint)

    def set_joint_goal(self, joint_state, weight=None, max_velocity=None):
        """
        :param joint_state:
        :type joint_state: dict
        """
        if not weight and not max_velocity:
            constraint = JointConstraint()
            constraint.type = JointConstraint.JOINT
            if isinstance(joint_state, dict):
                for joint_name, joint_position in joint_state.items():
                    constraint.goal_state.name.append(joint_name)
                    constraint.goal_state.position.append(joint_position)
            elif isinstance(joint_state, JointState):
                constraint.goal_state = joint_state
            self.cmd_seq[-1].joint_constraints.append(constraint)
        elif isinstance(joint_state, dict):
            for joint_name, joint_position in joint_state.items():
                constraint = Constraint()
                constraint.type = u'JointPosition'
                params = {}
                params[u'joint_name'] = joint_name
                params[u'goal'] = joint_position
                if weight:
                    params[u'weight'] = weight
                if max_velocity:
                    params[u'max_velocity'] = max_velocity
                constraint.parameter_value_pair = json.dumps(params)
                self.cmd_seq[-1].constraints.append(constraint)

    def align_planes(self, tip, tip_normal, root=None, root_normal=None):
        """
        :type tip: str
        :type tip_normal: Vector3Stamped
        :type root: str
        :type root_normal: Vector3Stamped
        :return:
        """
        root = root if root else self.get_root()
        tip_normal = convert_ros_message_to_dictionary(tip_normal)
        if not root_normal:
            root_normal = Vector3Stamped()
            root_normal.header.frame_id = self.get_root()
            root_normal.vector.z = 1
        root_normal = convert_ros_message_to_dictionary(root_normal)
        self.set_json_goal(u'AlignPlanes', tip=tip, tip_normal=tip_normal, root=root, root_normal=root_normal)

    def gravity_controlled_joint(self, joint_name, object_name):
        self.set_json_goal(u'GravityJoint', joint_name=joint_name, object_name=object_name)

    def update_god_map(self, updates):
        self.set_json_goal(u'UpdateGodMap', updates=updates)

    def update_yaml(self, updates):
        self.set_json_goal(u'UpdateYaml', updates=updates)

    def pointing(self, tip, goal_point, root=None, pointing_axis=None, weight=None):
        kwargs = {u'tip':tip,
                  u'goal_point':goal_point}
        if root is not None:
            kwargs[u'root'] = root
        if pointing_axis is not None:
            kwargs[u'pointing_axis'] = convert_ros_message_to_dictionary(pointing_axis)
        if weight is not None:
            kwargs[u'weight'] = weight
        kwargs[u'goal_point'] = convert_ros_message_to_dictionary(goal_point)
        self.set_json_goal(u'Pointing', **kwargs)

    def set_json_goal(self, constraint_type, **kwargs):
        constraint = Constraint()
        constraint.type = constraint_type
        for k, v in kwargs.items():
            if isinstance(v, Message):
                kwargs[k] = convert_ros_message_to_dictionary(v)
        constraint.parameter_value_pair = json.dumps(kwargs)
        self.cmd_seq[-1].constraints.append(constraint)

    def set_collision_entries(self, collisions):
        self.cmd_seq[-1].collisions.extend(collisions)

    def allow_collision(self, robot_links=(CollisionEntry.ALL,), body_b=CollisionEntry.ALL,
                        link_bs=(CollisionEntry.ALL,)):
        """
        :param robot_links: list of robot link names as str, None or empty list means all
        :type robot_links: list
        :param body_b: name of the other body, use the robots name to modify self collision behavior, empty string means all bodies
        :type body_b: str
        :param link_bs: list of link name of body_b, None or empty list means all
        :type link_bs: list
        """
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.ALLOW_COLLISION
        collision_entry.robot_links = [str(x) for x in robot_links]
        collision_entry.body_b = str(body_b)
        collision_entry.link_bs = [str(x) for x in link_bs]
        self.set_collision_entries([collision_entry])

    def avoid_collision(self, min_dist, robot_links=(CollisionEntry.ALL,), body_b=CollisionEntry.ALL,
                        link_bs=(CollisionEntry.ALL,)):
        """
        :param min_dist: the distance giskard is trying to keep between specified links
        :type min_dist: float
        :param robot_links: list of robot link names as str, None or empty list means all
        :type robot_links: list
        :param body_b: name of the other body, use the robots name to modify self collision behavior, empty string means all bodies
        :type body_b: str
        :param link_bs: list of link name of body_b, None or empty list means all
        :type link_bs: list
        """
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.AVOID_COLLISION
        collision_entry.min_dist = min_dist
        collision_entry.robot_links = [str(x) for x in robot_links]
        collision_entry.body_b = str(body_b)
        collision_entry.link_bs = [str(x) for x in link_bs]
        self.set_collision_entries([collision_entry])

    def allow_all_collisions(self):
        """
        Allows all collisions for next goal.
        """
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.ALLOW_COLLISION
        collision_entry.robot_links = [CollisionEntry.ALL]
        collision_entry.body_b = CollisionEntry.ALL
        collision_entry.link_bs = [CollisionEntry.ALL]
        self.set_collision_entries([collision_entry])

    def allow_self_collision(self):
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.ALLOW_COLLISION
        collision_entry.robot_links = [CollisionEntry.ALL]
        collision_entry.body_b = self.get_robot_name()
        collision_entry.link_bs = [CollisionEntry.ALL]
        self.set_collision_entries([collision_entry])

    def set_self_collision_distance(self, min_dist=0.05):
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.AVOID_COLLISION
        collision_entry.robot_links = [CollisionEntry.ALL]
        collision_entry.body_b = self.get_robot_name()
        collision_entry.link_bs = [CollisionEntry.ALL]
        collision_entry.min_dist = min_dist
        self.set_collision_entries([collision_entry])

    def avoid_all_collisions(self, distance=0.05):
        """
        Avoids all collisions for next goal.
        :param distance: the distance that giskard is trying to keep from all objects
        :type distance: float
        """
        collision_entry = CollisionEntry()
        collision_entry.type = CollisionEntry.AVOID_COLLISION
        collision_entry.robot_links = [CollisionEntry.ALL]
        collision_entry.body_b = CollisionEntry.ALL
        collision_entry.link_bs = [CollisionEntry.ALL]
        collision_entry.min_dist = distance
        self.set_collision_entries([collision_entry])

    def add_cmd(self, max_trajectory_length=20):
        move_cmd = MoveCmd()
        # move_cmd.max_trajectory_length = max_trajectory_length
        self.cmd_seq.append(move_cmd)

    def clear_cmds(self):
        """
        Removes all move commands from the current goal, collision entries are left untouched.
        """
        self.cmd_seq = []
        self.add_cmd()

    def plan_and_execute(self, wait=True):
        """
        :param wait: this function block if wait=True
        :type wait: bool
        :return: result from giskard
        :rtype: MoveResult
        """
        goal = self._get_goal()
        if wait:
            self.client.send_goal_and_wait(goal)
            return self.client.get_result()
        else:
            self.client.send_goal(goal)

    def plan(self, wait=True):
        """
        :param wait: this function block if wait=True
        :type wait: bool
        :return: result from giskard
        :rtype: MoveResult
        """
        goal = self._get_goal()
        goal.type = MoveGoal.PLAN_ONLY
        if wait:
            self.client.send_goal_and_wait(goal)
            return self.client.get_result()
        else:
            self.client.send_goal(goal)

    def get_collision_entries(self):
        return self.cmd_seq

    def _get_goal(self):
        goal = MoveGoal()
        goal.cmd_seq = self.cmd_seq
        goal.type = MoveGoal.PLAN_AND_EXECUTE
        self.clear_cmds()
        return goal

    def interrupt(self):
        self.client.cancel_goal()

    def get_result(self, timeout=rospy.Duration()):
        """
        Waits for giskardpy result and returns it. Only used when plan_and_execute was called with wait=False
        :type timeout: rospy.Duration
        :rtype: MoveResult
        """
        self.client.wait_for_result(timeout)
        return self.client.get_result()

    def clear_world(self):
        """
        :rtype: UpdateWorldResponse
        """
        req = UpdateWorldRequest(UpdateWorldRequest.REMOVE_ALL, WorldBody(), False, PoseStamped())
        return self.update_world.call(req)

    def remove_object(self, name):
        """
        :param name:
        :type name: str
        :return:
        :rtype: UpdateWorldResponse
        """
        object = WorldBody()
        object.name = str(name)
        req = UpdateWorldRequest(UpdateWorldRequest.REMOVE, object, False, PoseStamped())
        return self.update_world.call(req)

    def add_box(self, name=u'box', size=(1, 1, 1), frame_id=u'map', position=(0, 0, 0), orientation=(0, 0, 0, 1),
                pose=None):
        """
        :param name:
        :param size: (x length, y length, z length)
        :param frame_id:
        :param position:
        :param orientation:
        :param pose:
        :return:
        """
        box = make_world_body_box(name, size[0], size[1], size[2])
        if pose is None:
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.header.frame_id = str(frame_id)
            pose.pose.position = Point(*position)
            pose.pose.orientation = Quaternion(*orientation)
        req = UpdateWorldRequest(UpdateWorldRequest.ADD, box, False, pose)
        return self.update_world.call(req)

    def add_sphere(self, name=u'sphere', size=1, frame_id=u'map', position=(0, 0, 0), orientation=(0, 0, 0, 1),
                   pose=None):
        object = WorldBody()
        object.type = WorldBody.PRIMITIVE_BODY
        object.name = str(name)
        if pose is None:
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.header.frame_id = str(frame_id)
            pose.pose.position = Point(*position)
            pose.pose.orientation = Quaternion(*orientation)
        object.shape.type = SolidPrimitive.SPHERE
        object.shape.dimensions.append(size)
        req = UpdateWorldRequest(UpdateWorldRequest.ADD, object, False, pose)
        return self.update_world.call(req)

    def add_mesh(self, name=u'mesh', mesh=u'', frame_id=u'map', position=(0, 0, 0), orientation=(0, 0, 0, 1),
                 pose=None):
        object = WorldBody()
        object.type = WorldBody.MESH_BODY
        object.name = str(name)
        if pose is None:
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.header.frame_id = str(frame_id)
            pose.pose.position = Point(*position)
            pose.pose.orientation = Quaternion(*orientation)
        object.mesh = mesh
        req = UpdateWorldRequest(UpdateWorldRequest.ADD, object, False, pose)
        return self.update_world.call(req)

    def add_cylinder(self, name=u'cylinder', size=(1, 1), frame_id=u'map', position=(0, 0, 0), orientation=(0, 0, 0, 1),
                     pose=None):
        object = WorldBody()
        object.type = WorldBody.PRIMITIVE_BODY
        object.name = str(name)
        if pose is None:
            pose = PoseStamped()
            pose.header.stamp = rospy.Time.now()
            pose.header.frame_id = str(frame_id)
            pose.pose.position = Point(*position)
            pose.pose.orientation = Quaternion(*orientation)
        object.shape.type = SolidPrimitive.CYLINDER
        object.shape.dimensions.append(size[0])
        object.shape.dimensions.append(size[1])
        req = UpdateWorldRequest(UpdateWorldRequest.ADD, object, False, pose)
        return self.update_world.call(req)

    def attach_box(self, name=u'box', size=None, frame_id=None, position=None, orientation=None):
        """
        :type name: str
        :type size: list
        :type frame_id: str
        :type position: list
        :type orientation: list
        :rtype: UpdateWorldResponse
        """
        box = make_world_body_box(name, size[0], size[1], size[2])
        pose = PoseStamped()
        pose.header.stamp = rospy.Time.now()
        pose.header.frame_id = str(frame_id) if frame_id is not None else u'map'
        pose.pose.position = Point(*(position if position is not None else [0, 0, 0]))
        pose.pose.orientation = Quaternion(*(orientation if orientation is not None else [0, 0, 0, 1]))

        req = UpdateWorldRequest(UpdateWorldRequest.ADD, box, True, pose)
        return self.update_world.call(req)

    def attach_cylinder(self, name=u'cylinder', height=1, radius=1, frame_id=None, position=None, orientation=None):
        """
        :type name: str
        :type size: list
        :type frame_id: str
        :type position: list
        :type orientation: list
        :rtype: UpdateWorldResponse
        """
        cylinder = make_world_body_cylinder(name, height, radius)
        pose = PoseStamped()
        pose.header.stamp = rospy.Time.now()
        pose.header.frame_id = str(frame_id) if frame_id is not None else u'map'
        pose.pose.position = Point(*(position if position is not None else [0, 0, 0]))
        pose.pose.orientation = Quaternion(*(orientation if orientation is not None else [0, 0, 0, 1]))

        req = UpdateWorldRequest(UpdateWorldRequest.ADD, cylinder, True, pose)
        return self.update_world.call(req)

    def attach_object(self, name, link_frame_id):
        """
        :type name: str
        :type link_frame_id: str
        :return: UpdateWorldResponse
        """
        req = UpdateWorldRequest()
        req.rigidly_attached = True
        req.body.name = name
        req.pose.header.frame_id = link_frame_id
        req.operation = UpdateWorldRequest.ADD
        return self.update_world.call(req)

    def detach_object(self, object_name):
        req = UpdateWorldRequest()
        req.body.name = object_name
        req.operation = req.DETACH
        return self.update_world.call(req)

    def add_urdf(self, name, urdf, pose, js_topic=u''):
        urdf_body = WorldBody()
        urdf_body.name = str(name)
        urdf_body.type = WorldBody.URDF_BODY
        urdf_body.urdf = str(urdf)
        urdf_body.joint_state_topic = str(js_topic)
        req = UpdateWorldRequest(UpdateWorldRequest.ADD, urdf_body, False, pose)
        if js_topic:
            # FIXME publisher has to be removed, when object gets deleted
            # FIXME there could be sync error, if objects get added/removed by something else
            self.object_js_topics[name] = rospy.Publisher(js_topic, JointState, queue_size=10)
        return self.update_world.call(req)

    def set_object_joint_state(self, object_name, joint_states):
        if isinstance(joint_states, dict):
            joint_states = dict_to_joint_states(joint_states)
        self.object_js_topics[object_name].publish(joint_states)

    def get_object_names(self):
        """
        returns the name of every object in the world
        :rtype: GetObjectNamesResponse
        """
        return self.get_object_names()

    def get_object_info(self, name):
        """
        returns the joint state, joint state topic and pose of the object with the given name
        :type name: str
        :rtype: GetObjectInfoResponse
        """
        return self.get_object_info(name)

    def update_rviz_markers(self, object_names):
        """
        republishes visualization markers for rviz
        :type name: list
        :rtype: UpdateRvizMarkersResponse
        """
        return self.update_rviz_markers(object_names)

    def get_attached_objects(self):
        """
        returns a list of all objects that are attached to the robot and the respective attachement points
        :rtype: GetAttachedObjectsResponse
        """
        return self.get_attached_objects()



