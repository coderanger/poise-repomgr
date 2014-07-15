#
# Copyright 2014, Noah Kantrowitz
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import collections
import json
import os
import re
import tempfile

import treq
from characteristic import attributes
from depot.apt import AptPackages, AptRepository
from depot.gpg import GPG
from depot.storage import StorageWrapper
from twisted import python
from twisted.internet import defer, task, threads, reactor
from klein import Klein

RELEASES_URI = 'https://www.getchef.com/chef/full_{}_list'
PACKAGES_URI = 'https://opscode-omnibus-packages.s3.amazonaws.com{}'
ALLOWED_VERSIONS = re.compile(r'^\d+\.\d+\.\d+(-\d+)?$')

CODENAMES = {
    'debian': {
        '6': 'squeeze',
        '7': 'wheezy',
    },
    'ubuntu': {
        '10.04': 'lucid',
        '10.10': 'maverick',
        '11.04': 'natty',
        '11.10': 'oneric',
        '12.04': 'precise',
        '12.10': 'quantal',
        '13.04': 'raring',
        '13.10': 'saucy',
        '14.04': 'trusty',
    },
}

@attributes(['platform', 'platform_version', 'arch', 'version', 'opscode_path'])
class Release(object):
    @property
    def codename(self):
        return CODENAMES[self.platform][self.platform_version]

    @property
    def component(self):
        return 'chef-{}'.format(self.version.split('.')[0])

    @property
    def pool_path(self):
        return 'pool/{}-{}/{}'.format(self.platform, self.platform_version, self.opscode_path.split('/')[-1])

    @property
    def opscode_uri(self):
        return PACKAGES_URI.format(self.opscode_path)

    @property
    def debian_arch(self):
        return {'x86_64': 'amd64', 'i686': 'i386'}.get(self.arch, self.arch)

    def to_json(self):
        return {
            'platform': self.platform,
            'platform_version': self.platform_version,
            'arch': self.arch,
            'version': self.version,
            'opscode_path': self.opscode_path,
        }


class WorkerQueue(object):
    def __init__(self, fn, max=1):
        self._queue = collections.deque()
        self._fn = fn
        self._active = 0
        self._max = max

    def tasks(self):
        return [x[1] for x in self._queue]

    def enqueue(self, data):
        d = defer.Deferred()
        self._queue.append((d, data))
        self._work()
        return d

    def _work(self):
        if self._active >= self._max or not self._queue:
            return
        self._active += 1
        d, data = self._queue.popleft()
        d2 = defer.succeed(data)
        d2.addCallback(self._fn)
        d2.chainDeferred(d)
        d2.addCallback(self._complete)

    def _complete(self, _):
        self._active -= 1
        self._work()


class JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Release):
            return obj.to_json()
        return super(JSONEncoder, self).default(obj)


class RepoMgr(object):
    app = Klein()

    def __init__(self):
        # Initialize apt storage backend
        self._storage_uri = os.environ.get('STORAGE_URI', 'local://')
        self._storage = StorageWrapper(self._storage_uri)
        # If $SIGNING_KEY is set, we are running on Heroku so import it to ./
        self._gpg = GPG(os.environ.get('SIGNING_KEY_ID'),
                        key=os.environ.get('SIGNING_KEY'),
                        home='.' if 'SIGNING_KEY' in os.environ else None)

        # State data
        self._releases = set()
        self._queue = WorkerQueue(self._sync_release)

        # Give things 60 seconds to stabilize before re start crawling
        reactor.callLater(60, self._start_cron)

    @app.route('/')
    def items(self, request):
        request.setHeader('Content-Type', 'application/json')
        return json.dumps({'releases': sorted(self._releases), 'queue': self._queue.tasks()}, cls=JSONEncoder, sort_keys=True)

    def _start_cron(self):
        # Start up looping task every N seconds
        self._cron_task = task.LoopingCall(self._cron)
        self._cron_task.start(300)

    def _cron(self):
        self._fetch_releases('client')

    def _fetch_releases(self, flavor):
        d = treq.get(RELEASES_URI.format(flavor))
        d.addCallback(treq.json_content)
        d.addCallback(self._diff_releases, flavor)
        return d

    def _diff_releases(self, full_releases, flavor):
        # SUPER DIAGONAL CODE GO
        for platform, platform_data in full_releases.iteritems():
            if platform != 'debian' and platform != 'ubuntu':
                continue # Ignore non-debs
            for platform_version, platform_version_data in platform_data.iteritems():
                for arch, arch_data in platform_version_data.iteritems():
                    for version, path in arch_data.iteritems():
                        if not ALLOWED_VERSIONS.match(version):
                            continue # Skip RCs and Betas and whatnot
                        release = Release(platform=platform,
                                          platform_version=platform_version,
                                          arch=arch,
                                          version=version,
                                          opscode_path=path)
                        # Need to handle flavor here
                        if release not in self._releases:
                            self._queue.enqueue(release)
                        self._releases.add(release)

    def _sync_release(self, release):
        d = threads.deferToThread(self._get_packages_manifest, release)
        d.addCallback(self._check_release, release)
        return d

    def _get_packages_manifest(self, release):
        packages_path = 'dists/{}/{}/binary-{}/Packages'.format(release.codename, release.component, release.debian_arch)
        print('Retrieving manifest from {}'.format(packages_path))
        return AptPackages(self._storage, self._storage.download(packages_path, skip_hash=True) or '')

    def _check_release(self, packages, release):
        for pkg in packages.packages.itervalues():
            if pkg['Filename'] == release.pool_path:
                return
        print('No match on {}, downloading'.format(release.pool_path))
        return self._download_release(release)

    def _download_release(self, release):
        temp = tempfile.NamedTemporaryFile()
        print('Fetching {} to {}'.format(release.opscode_uri, temp.name))
        d = treq.get(release.opscode_uri)
        d.addCallback(treq.collect, temp.write)
        d.addCallback(self._upload_release, release, temp)
        d.addBoth(lambda _: (temp.close(), _)[1]) # Funky syntax to not swallow errors
        d.addErrback(python.log.err)
        return d

    def _upload_release(self, _, release, temp):
        def fn():
            print('Uploading {}'.format(release.opscode_path))
            temp.seek(0, 0)
            repo =  AptRepository(self._storage, self._gpg, release.codename, release.component)
            repo.add_package(release.opscode_path, temp, force=True, pool_path=release.pool_path)
            repo.commit_metadata()
        return threads.deferToThread(fn)


# So we can use twistd
repo_mgr = RepoMgr()
resource = repo_mgr.app.resource

if __name__ == '__main__':
    repo_mgr.app.run('0.0.0.0', int(os.environ.get('PORT', 8000)))
