# =============================================================================
# Copyright [2013] [Kevin Carter]
# License Information :
# This software has no warranty, it is provided 'as is'. It is your
# responsibility to validate the behavior of the routines and its accuracy
# using the code provided. Consult the GNU General Public license for further
# details (see GNU General Public License).
# http://www.gnu.org/licenses/gpl.html
# =============================================================================
import multiprocessing

from tribble import builder


def execute():
    """Execute the Tribble Application."""
    user_args = builder.arguments()
    datacenters = user_args['region'].split(',')
    user_args['threads'] /= len(datacenters)
    for dc in datacenters:
        # Start Action Thread
        action = (user_args, dc)
        multiprocessing.Process(target=builder.runner, args=action).start()


if __name__ == "__main__":
    execute()
