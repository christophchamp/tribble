Rackspace Cloud Builder
#######################
:date: 2012-09-20 05:54
:tags: rackspace, build, mass, deployment, api, cloud, server, python
:category: linux 

Build a lot of Cloud Servers all at once
========================================

If you have found yourself in a situation where you needed to build a bunch of Cloud Servers, and you needed that done in multiple data centers all at the same time, this is the application that you have been looking for. This system uses the Next Generation Rackspace Open Cloud to deploy your Instances.

Prerequisites :
  * Python => 2.6 but < 3.0
  * Python Novaclient >= 2.15.0.0

--------

General Overview
^^^^^^^^^^^^^^^^

To use this application you will need the following:
  * A Rackspace Cloud Account
  * An Image you want to build with, Preferably use the "name", but the "UUID" will also work
  * A Flavor Size, ID number
  * A Region to build in, This can be multiple regions if you want
  * The will to want to build lots of servers
  

How to make it all go::

  builder -U <user> -P <apikey> -R ord --image <imageID> --flavor <flavorID> -bn <NumServers> --name <ServerName> build
  

Other Functions:
  :get-ips: Get all of the IPs for all of the instances that have been built with your naming convention
  :destroy: Destroy all instances that have been built with your naming convention

--------

License :
  This program is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details. See "README/LICENSE.txt" for full disclosure of the license associated with this product. Or goto http://www.gnu.org/licenses/

