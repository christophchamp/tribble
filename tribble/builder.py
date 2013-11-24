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

from novaclient.v1_1 import client as nova_client


POST_ACTION = """
Done. If everything worked as expected, Here is what you have
=============================================================

The was done for account "%(username)s"

Servers  = %(build_number)s
Password = %(server_password)s
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
    par.add_argument('-N', '--name',
                     metavar='',
                     help='Naming convention for the server you want to build',
                     required=False,
                     default='Server')
    par.add_argument('-I', '--image',
                     metavar='',
                     help='The servers Image Name or ID',
                     required=False,
                     default=None)
    par.add_argument('-F', '--flavor',
                     metavar='',
                     type=int,
                     help='The Servers Flavor Size, DEFAULT: %(default)s',
                     required=False,
                     default=2)
    par.add_argument('-sp',
                     '--server-password',
                     metavar='',
                     help=('Admin password for servers.'
                           ' DEFAULT: "%(default)s"'),
                     required=False,
                     default='secrete')
    par.add_argument('-bn',
                     '--build-number',
                     metavar='',
                     type=int,
                     help='Number of servers, DEFAULT: %(default)s',
                     required=False,
                     default=1)
    par.add_argument('--threads',
                     metavar='',
                     type=int,
                     help='Rate of Concurrency, DEFAULT: %(default)s',
                     required=False,
                     default=10)
    par.add_argument('--key-name',
                     metavar='',
                     type=str,
                     help='Name of key to be injected into your Servers',
                     required=False,
                     default=None)
    par.add_argument('--key-location',
                     metavar='',
                     type=str,
                     help=('Location of the public key to be saved into'
                           ' nova for key injection into your servers.'
                           ' If your key-name does not exists and this'
                           ' variables file path is found the key will be'
                           ' created for you, DEFAULT: "%(default)s"'),
                     required=False,
                     default='~/.ssh/id_rsa.pub')

    # Add a subparser
    subpar = par.add_subparsers()

    # Builder args
    build = subpar.add_parser('build',
                              help='Build instances')
    build.set_defaults(build=True)

    # Destoryer args
    destroy = subpar.add_parser('destroy',
                                help='Destroy instances')
    destroy.set_defaults(destroy=True)

    # Destoryer args
    get_ips = subpar.add_parser('get-ips',
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


def bob_the_builder(client, args, number, queue, fault=0):
    """Build Instances."""

    def _kill(nova, server_id, num, work_queue):
        work_queue.put(num)
        time.sleep(1)
        nova.servers.delete(server_id)

    kwargs = {
        'name': '%s_%s' % (args['name'], number),
        'image': args['imageid'],
        'flavor': args['flavor'],
        'admin_pass': args['server_password']
    }

    if args.get('key_name'):
        if not client.keypairs.findall(name=args['key_name']):
            if os.path.exists(args['key_location']):
                keyfile = os.path.expanduser(args['key_location'])
                with open(keyfile, 'rb') as key:
                    client.keypairs.create(
                        name=args['key_name'],
                        public_key=key.read()
                    )
            else:
                kwargs['key_name'] = args['key_name']
        else:
            kwargs['key_name'] = args['key_name']

    time.sleep(random.randrange(1, 5))
    while True:
        try:
            instance = client.servers.create(**kwargs)
        except Exception, exc:
            fault += 1
            print('EXCEPTION in build process: "%s" The application will retry,'
                  ' Number of faults "%s"' % (exc, fault))
            # Retry on Exception
            if fault >= 10:
                raise SystemExit('Too many fatal error happened while building'
                                 ' your servers.')
            else:
                time.sleep(5)
        else:
            status = instance.status
            break

    tryout = 100
    tries = 0

    while status != 'ACTIVE':
        time.sleep(10)
        tries += 1

        # Retrieve the instance again so the status field updates
        instance = client.servers.get(instance.id)
        status = instance.status
        idnum = instance.id

        if status == 'ERROR':
            print('%s is in ERROR and will be deleted. '
                  'The job for server number %s will be requeued.'
                  % (idnum, number))
            _kill(client, idnum, number, queue)
            break
        elif tries >= tryout:
            print('In buidling server "%s" we hit a the max attempts of %s we'
                  ' will delete this instance and try again'
                  % (idnum, tryout))
            _kill(client, idnum, number, queue)
            break
    else:
        print('Instance ID %s Name %s is ACTIVE'
              % (instance.id, instance.name))


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


def runner(args, client, region, image):
    """Run the application process from within the thread.

    :param
    """
    if args.get('build') is True:
        # Load the queue
        queue = basic_queue(iters=range(args['build_number']))

        args['imageid'] = image
        args['dc'] = region

        # Prep the threader
        worker_proc(job_action=bob_the_builder,
                    queue=queue,
                    client=client,
                    args=args,
                    job=doerator)

        queue.close()
        print(POST_ACTION % args)
    elif args.get('destroy') is True:
        servers = [server.id for server in client.servers.list()
                   if server.name.startswith(args['name'])]
        for server in servers:
            client.servers.delete(server)
    elif args.get('get_ips') is True:
        servers = [(server.status, server.accessIPv4)
                   for server in client.servers.list()
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
        raise SystemExit('died because something bad happened.')
