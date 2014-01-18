#!/usr/bin/env python
# =============================================================================
# Copyright [2013] [Kevin Carter]
# License Information :
# This software has no warranty, it is provided 'as is'. It is your
# responsibility to validate the behavior of the routines and its accuracy
# using the code provided. Consult the GNU General Public license for further
# details (see GNU General Public License).
# http://www.gnu.org/licenses/gpl.html
# =============================================================================

try:
    import argparse
except ImportError:
    raise SystemExit('Python module "argparse" not Found for import.')
import multiprocessing
import os
import Queue
import random
import time
import uuid

from novaclient.v1_1 import client as nova_client


MAX_FAULTS = 10
POST_ACTION = """
Done. If everything worked as expected, Here is what you have
=============================================================

The was done for account "%(username)s"

Servers  = %(number)s
Password = %(admin_pass)s
Region = %(dc)s

run: get-ips for the regions you just built
"""


def arguments():
    """Parse the Command Line Arguments."""

    par = argparse.ArgumentParser(
        usage='%(prog)s',
        description=(
            '%(prog)s Build lots of Rackspace Cloud Servers.'
        ),
        epilog='GPLv3 Licensed.'
    )

    name = argparse.ArgumentParser(add_help=False)
    name.add_argument('--name',
                      metavar='',
                      help='Naming convention',
                      required=True,
                      default=None)

    key = argparse.ArgumentParser(add_help=False)
    key.add_argument('--key-name',
                     metavar='',
                     help=('Name of key to be injected into your Servers. If'
                           ' the key name is not found and the key-location'
                           ' is, a key will be created for you in NOVA and'
                           ' injected.'),
                     default=None)

    par.add_argument('-U',
                     '--username',
                     metavar='',
                     help='Your Username',
                     required=True,
                     default=None)
    par.add_argument('-P',
                     '--password',
                     metavar='',
                     help='Your Password',
                     required=True,
                     default=None)
    par.add_argument('-R',
                     '--region',
                     metavar='',
                     help='Your Region, use commas to separate regions',
                     required=True,
                     default=None)
    par.add_argument('--threads',
                     metavar='',
                     type=int,
                     help='Rate of Concurrency, DEFAULT: %(default)s',
                     required=False,
                     default=10)
    par.add_argument('--key-location',
                     metavar='',
                     help=('Location of the public key to be saved into'
                           ' nova for key injection into your servers.'
                           ' If your key-name does not exists and this'
                           ' variables file path is found the key will be'
                           ' created for you, DEFAULT: "%(default)s"'),
                     default='~/.ssh/id_rsa.pub')
    # Add a subparser
    subpar = par.add_subparsers()

    # Builder args
    bld = subpar.add_parser('build',
                            parents=[name, key],
                            help='Build instances')
    bld.set_defaults(build=True)
    bld.add_argument('-i',
                     '--image',
                     metavar='',
                     help='The servers Image Name or ID',
                     required=False,
                     default=None)
    bld.add_argument('-f',
                     '--flavor',
                     metavar='',
                     type=int,
                     help='The Servers Flavor Size, DEFAULT: %(default)s',
                     required=False,
                     default=2)
    bld.add_argument('-a',
                     '--admin-pass',
                     metavar='',
                     help=('Admin password for servers.'
                           ' DEFAULT: "%(default)s"'),
                     required=False,
                     default='secrete')
    bld.add_argument('-n',
                     '--number',
                     metavar='',
                     type=int,
                     help='Number of servers, DEFAULT: %(default)s',
                     required=False,
                     default=1)

    # Destoryer args
    dst = subpar.add_parser('destroy',
                            parents=[name],
                            help='Destroy instances')
    dst.set_defaults(destroy=True)

    # Destoryer args
    get_ips = subpar.add_parser('get-ips',
                                parents=[name],
                                help='Get all server IPs')
    get_ips.set_defaults(get_ips=True)

    return vars(par.parse_args())


class auth_plugin(object):
    def __init__(self):
        """Craetes an authentication plugin for use with Rackspace."""

        self.auth_url = self.global_auth()

    def global_auth(self):
        """Return the Rackspace Cloud US Auth URL."""

        return "https://identity.api.rackspacecloud.com/v2.0/"

    def _authenticate(self, cls, auth_url):
        """Authenticate against the Rackspace auth service."""

        body = {"auth": {
            "RAX-KSKEY:apiKeyCredentials": {
                "username": cls.user,
                "apiKey": cls.password,
                "tenantName": cls.projectid}}}
        return cls._authenticate(auth_url, body)

    def authenticate(self, cls, auth_url):
        """Authenticate against the Rackspace US auth service."""

        return self._authenticate(cls, auth_url)


class rax_creds(object):
    def __init__(self, user, apikey, region):
        """Set our creds in a Class for use later.

        :param user:
        :param apikey:
        :param region:
        """

        self.user = user
        self.apikey = apikey
        self.region = region
        self.system = 'rackspace'
        self.plugin = auth_plugin()


class Clients(object):
    def __init__(self, creds):
        """Load our client.

        :param creds:
        """
        self.creds = creds
        insecure = False
        cacert = None
        self.creds_dict = dict(
            username=self.creds.user,
            api_key=self.creds.apikey,
            project_id=self.creds.user,
            region_name=self.creds.region,
            insecure=insecure,
            cacert=cacert,
            auth_url=self.creds.plugin.auth_url,
        )

    def novaclient(self):
        """Load the Novaclient."""

        self.creds_dict.update({
            'auth_system': self.creds.system,
            'auth_plugin': self.creds.plugin
        })
        client = nova_client.Client(**self.creds_dict)
        return client

    def get_client(self, client):
        """Get the Client that we need.

        :param client: str
        """

        # Setup our RAX Client
        client_type = getattr(self, client)
        if client_type is None:
            raise SystemExit('No Client Type Found')
        else:
            return client_type()


def wait_for_active(client, number, queue, sid, status, tries=0):
    """Wait for the instance to be active."""

    def _kill_server(nova, server_id, num, work_queue):
        work_queue.put(num)
        time.sleep(1)
        client_delete(client=nova, server_id=server_id)

    time.sleep(10)
    tries += 1

    # Retrieve the instance again so the status field updates
    instance = client_server_get(client, server_id=sid)
    status = instance.status
    idnum = instance.id

    if status == 'ACTIVE':
        print('Instance ID %s Name %s is ACTIVE'
              % (instance.id, instance.name))
        return instance
    elif status == 'ERROR':
        print('%s is in ERROR and will be deleted. '
              'The job for server number %s will be requeued.'
              % (idnum, number))
        _kill_server(client, idnum, number, queue)
    elif tries >= MAX_FAULTS * 10:
        print('In buidling server "%s" we hit a the max attempts of %s we'
              ' will delete this instance and try again' % (idnum, MAX_FAULTS))
        _kill_server(client, idnum, number, queue)
    else:
        wait_for_active(client, number, queue, sid, status, tries)


def bob_the_builder(client, args, number, queue):
    """Build Instances."""

    _uuid = str(uuid.uuid4()).split('-')[0]
    args['kwargs']['name'] = '%s_%s_%s' % (args['name'], args['dc'], _uuid)

    # Build our instance
    instance = client_create(client, build_hash=args['kwargs'])
    if instance is None:
        bob_the_builder(client, args, number, queue)
    else:
        instance_id = instance.id
        instance_status = 'BUILD'
        # Wait until the instance reports active
        wait_for_active(client, number, queue, instance_id, instance_status)


def basic_queue(iters=None):
    """Uses a manager Queue, from multiprocessing.

    All jobs will be added to the queue for processing.
    :param iters:
    """

    worker_q = multiprocessing.Queue()
    if iters is not None:
        for _dt in iters:
            worker_q.put(_dt)
    return worker_q


def worker_proc(job_action, queue, client, args, job):
    """Requires the job_action and num_jobs variables for functionality.

    :param job_action: What function will be used
    :param queue: The Queue

    All threads produced by the worker are limited by the number of concurrency
    specified by the user. The Threads are all made active prior to them
    processing jobs.
    """

    add_args = [queue, client, args, job_action]
    jobs = [multiprocessing.Process(target=job,
                                    args=tuple(add_args))
            for _ in xrange(args['threads'])]

    join_jobs = []
    for _job in jobs:
        time.sleep(.1)
        join_jobs.append(_job)
        _job.start()

    for job in join_jobs:
        job.join()


def get_from_q(queue):
    """Returns the file or a sentinel value.

    :param queue:
    :return item|None:
    """

    try:
        wfile = queue.get(timeout=5)
    except Queue.Empty:
        return None
    else:
        return wfile


def doerator(queue, client, args, job_action):
    """Do Jobs until done."""

    job = job_action
    while True:
        # Get the file that we want to work with
        wfile = get_from_q(queue=queue)

        # If Work is None return None
        if wfile is None:
            break

        # Do the job that was provided
        job(client, args, wfile, queue)


def job_check(args, client, tries=0):
    all_servers = client_list(client)
    if all_servers:
        server_count = len(all_servers)
        #
        # Commenting out this section since we don't want it to
        # nuke our new servers.
        #
        #if server_count > args['number']:
        #    diff = server_count - args['number']
        #    print('Too many severs found, we should have "%s"'
        #          ' but we have "%s" The system will now normalize.'
        #          % (args['number'], server_count))
        #    servers_ids = [server.id for server in client_list(client)
        #                   if server.name.startswith(args['name'])]
        #    for server_id in servers_ids[:diff]:
        #        client_delete(client, server_id=server_id)
    else:
        if tries > MAX_FAULTS:
            raise SystemExit('The system had too many failures, while'
                             ' performing a job check')
        else:
            time.sleep(.5)
            job_check(args, client)


def client_list(client, fault=0):
    """Return a list of Servers."""

    try:
        servers = client.servers.list()
    except Exception as exc:
        fault += 1
        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT LIST: "%s", FAULT: %s' % (exc, fault))
            raise SystemExit('The system had too many failures')
        else:
            client_list(client, fault=fault)
    else:
        if servers is not None:
            return servers
        else:
            client_list(client)


def client_delete(client, server_id, fault=0):
    """Delete a server."""

    try:
        client.servers.delete(server_id)
    except Exception as (exc, tb):
        fault += 1
        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT DELETE: "%s", FAULT: %s' % (exc, tb))
            raise SystemExit('The system had too many failures')
        else:
            client_delete(client, server_id, fault=fault)


def client_create(client, build_hash, fault=0):
    """Return a list of Servers."""

    server = None
    try:
        time.sleep(random.randrange(1, 5))
        server = client.servers.create(**build_hash)
        if server is None:
            raise ValueError('Server Created returned a None Value.')
    except Exception as exc:
        fault += 1
        if server is not None:
            client_delete(client, server_id=server.id)

        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT CREATE: "%s", FAULT: %s' % (exc, fault))
            raise SystemExit('The system had too many failures')
        else:
            client_create(client, build_hash, fault=fault)
    else:
        return server


def client_server_get(client, server_id, fault=0):
    """Return a list of Servers."""

    try:
        server = client.servers.get(server_id)
    except Exception as exc:
        fault += 1
        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT CREATE: "%s", FAULT: %s' % (exc, fault))
            raise SystemExit('The system had too many failures')
        else:
            client_server_get(client, server_id, fault=fault)
    else:
        if server is not None:
            return server
        else:
            fault += 1
            client_server_get(client, server_id, fault=fault)


def client_key_find(client, key_name, fault=0):
    """See if a Key exists in Nova.

    :return True||False:
    """

    try:
        key = client.keypairs.findall(name=key_name)
    except Exception as exc:
        fault += 1
        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT KEY NAME LOOKUP: "%s", FAULT: %s'
                  % (exc, fault))
            raise SystemExit('The system had too many failures')
        else:
            client_key_find(client, key_name, fault=fault)
    else:
        return key


def client_key_create(client, key_name, public_key, fault=0):
    """Create a Public Key for Server injection in NOVA."""

    try:
        client.keypairs.create(name=key_name, public_key=public_key)
    except Exception as exc:
        fault += 1
        if fault > MAX_FAULTS:
            print('ERROR IN CLIENT KEY CREATE: "%s", FAULT: %s' % (exc, fault))
            raise SystemExit('The system had too many failures')
        else:
            client_key_create(client, key_name, public_key, fault=fault)


def runner(args, region):
    """Run the application process from within the thread.

    :param
    """
    creds = rax_creds(
        user=args['username'],
        apikey=args['password'],
        region=region
    )
    # Get the client
    nova = Clients(creds=creds).novaclient()
    image = args.get('image')
    if image is not None:
        image_ids = [img.id for img in nova.images.list()
                     if image in img.name or image == img.id]
        if image_ids:
            if len(image_ids) > 1:
                raise SystemExit('We found more than one image with'
                                 ' id/name of "%s" You are going to be'
                                 ' more specific'
                                 % image)
            else:
                image_id = image_ids[0]
        else:
            raise SystemExit('Image id/name "%s" was not found in Region'
                             ' "%s" You may want to try using the image'
                             ' name instead of the ID' % (image, region))
    else:
        image_id = None

    if args.get('build') is True:
        args['imageid'] = image_id
        args['dc'] = region

        args['kwargs'] = {
            'image': args['imageid'],
            'flavor': args['flavor'],
            'admin_pass': args['admin_pass']
        }

        if args.get('key_name'):
            if not client_key_find(nova, key_name=args['key_name']):
                key_path = os.path.expanduser(args['key_location'])
                if os.path.exists(key_path):
                    with open(key_path, 'rb') as key:
                        client_key_create(
                            nova,
                            key_name=args['key_name'],
                            public_key=key.read()
                        )
                    args['kwargs']['key_name'] = args['key_name']
            else:
                args['kwargs']['key_name'] = args['key_name']

        # Load the queue
        queue = basic_queue(iters=range(args['number']))

        # Prep the threader
        worker_proc(job_action=bob_the_builder,
                    queue=queue,
                    client=nova,
                    args=args,
                    job=doerator)
        queue.close()

        # Check that we have as many servers as we specified
        job_check(args, nova)

        # Show some information
        print(POST_ACTION % args)

    elif args.get('destroy') is True:
        servers = [server.id for server in client_list(nova)
                   if server.name.startswith(args['name'])]
        for server in servers:
            client_delete(nova, server_id=server)

    elif args.get('get_ips') is True:
        servers = [(server.status, server.accessIPv4)
                   for server in client_list(nova)
                   if server.name.startswith(args['name'])]
        filename = '%s_server_ips' % region
        if os.path.exists(filename):
            os.remove(filename)

        with open(filename, 'wb') as ips:
            for server in servers:
                state, ip = server
                if state == 'ACTIVE':
                    if ip:
                        ips.writelines('%s\n' % ip)

    else:
        raise SystemExit('Died because something bad happened.')
