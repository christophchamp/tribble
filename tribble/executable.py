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
        creds = builder.rax_creds(
            user=user_args['username'],
            apikey=user_args['password'],
            region=dc
        )
        # Get the client
        nova = builder.Clients(creds=creds).novaclient()

        _image = user_args['image']
        if _image is not None:
            image_ids = [img.id for img in nova.images.list()
                         if _image in img.name or _image == img.id]
            if image_ids:
                if len(image_ids) > 1:
                    raise SystemExit('We found more than one image with'
                                     ' id/name of "%s" You are going to be'
                                     ' more specific'
                                     % _image)
                else:
                    image_id = image_ids[0]
            else:
                raise SystemExit('Image id/name "%s" was not found in Region'
                                 ' "%s" You may want to try using the image'
                                 ' name instead of the ID' % (_image, dc))
        else:
            image_id = None
        # Start Action Thread
        action = (user_args, nova, dc, image_id)
        multiprocessing.Process(target=builder.runner, args=action).start()


if __name__ == "__main__":
    execute()
