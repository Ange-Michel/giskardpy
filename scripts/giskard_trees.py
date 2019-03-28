#!/usr/bin/env python
import rospy
from giskardpy.garden import grow_tree
from giskardpy.utils import check_dependencies

# TODO add pytest to package xml
# TODO add transform3d to package xml
# TODO do an additional sync round after goal received


if __name__ == u'__main__':
    rospy.init_node(u'giskard')
    check_dependencies()
    tree_tick_rate = 1. / rospy.get_param(u'~tree_tick_rate')
    tree = grow_tree()

    sleeper = rospy.Rate(tree_tick_rate)
    while not rospy.is_shutdown():
        try:
            tree.tick()
            sleeper.sleep()
        except KeyboardInterrupt:
            break
    print(u'\n')
