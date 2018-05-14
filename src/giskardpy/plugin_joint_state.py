from Queue import Empty, Queue
from collections import OrderedDict

import rospy

from sensor_msgs.msg import JointState

from giskardpy.plugin import Plugin
from giskardpy.trajectory import SingleJointState


class JointStatePlugin(Plugin):
    # TODO implement chain
    def __init__(self, js_identifier='js', time_identifier='time', next_cmd_identifier='motor'):
        super(JointStatePlugin, self).__init__()
        self.js_identifier = js_identifier
        self.time_identifier = time_identifier
        self.next_cmd_identifier = next_cmd_identifier
        self.js = None
        self.mjs = None
        self.lock = Queue(maxsize=1)

    def cb(self, data):
        try:
            self.lock.get_nowait()
        except Empty:
            pass
        self.lock.put(data)

    def get_readings(self):
        try:
            if self.mjs is None:
                js = self.lock.get_nowait()
            else:
                js = self.lock.get_nowait()
            self.mjs = OrderedDict()
            for i, joint_name in enumerate(js.name):
                sjs = SingleJointState()
                sjs.name = joint_name
                sjs.position = js.position[i]
                sjs.velocity = js.velocity[i]
                sjs.effort = js.effort[i]
                self.mjs[joint_name] = sjs
        except Empty:
            pass
        return {self.js_identifier: self.mjs}

    def start_always(self):
        self.joint_state_sub = rospy.Subscriber('joint_states', JointState, self.cb, queue_size=1)

    def stop(self):
        self.joint_state_sub.unregister()

    def update(self):
        pass

    def copy(self):
        return KinematicSimPlugin(js_identifier=self.js_identifier, next_cmd_identifier=self.next_cmd_identifier,
                                  time_identifier=self.time_identifier)


class KinematicSimPlugin(Plugin):
    def __init__(self, js_identifier='js', next_cmd_identifier='motor', time_identifier='time'):
        self.js_identifier = js_identifier
        self.next_cmd_identifier = next_cmd_identifier
        self.time_identifier = time_identifier
        self.frequency = 0.1
        self.time = -self.frequency
        super(KinematicSimPlugin, self).__init__()

    def get_readings(self):
        updates = {}
        if self.next_js is not None:
            updates[self.js_identifier] = self.next_js
        updates[self.time_identifier] = self.time
        return updates

    def update(self):
        self.time += self.frequency
        motor_commands = self.god_map.get_data(self.next_cmd_identifier)
        if motor_commands is not None:
            current_js = self.god_map.get_data(self.js_identifier)
            self.next_js = OrderedDict()
            for joint_name, sjs in current_js.items():
                if joint_name in motor_commands:
                    cmd = motor_commands[joint_name]
                else:
                    cmd = 0.0
                self.next_js[joint_name] = SingleJointState(sjs.name, sjs.position + cmd * self.frequency, velocity=cmd)

    def start_always(self):
        self.next_js = None

    def stop(self):
        pass

    def create_parallel_universe(self):
        return super(KinematicSimPlugin, self).create_parallel_universe()

    def end_parallel_universe(self):
        return super(KinematicSimPlugin, self).end_parallel_universe()

    def copy(self):
        return self