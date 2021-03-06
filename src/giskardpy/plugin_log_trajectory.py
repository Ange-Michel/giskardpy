from py_trees import Status

from giskardpy import identifier
from giskardpy.plugin import GiskardBehavior


class LogTrajPlugin(GiskardBehavior):
    def update(self):
        current_js = self.get_god_map().safe_get_data(identifier.joint_states)
        time = self.get_god_map().safe_get_data(identifier.time)
        trajectory = self.get_god_map().safe_get_data(identifier.trajectory)
        trajectory.set(time, current_js)
        self.get_god_map().safe_set_data(identifier.trajectory, trajectory)
        return Status.RUNNING
