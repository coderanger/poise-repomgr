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

from pytest import fixture

from main import Release, ALLOWED_VERSIONS

@fixture
def release1():
    return Release(platform='debian',
                   platform_version='6',
                   arch='x86_64',
                   version='10.12.0-1',
                   opscode_path='/debian/6/x86_64/chef_10.12.0-1.debian.6.0.5_amd64.deb')

@fixture
def release2():
    return Release(platform='ubuntu',
                   platform_version='12.04',
                   arch='x86_64',
                   version='11.8.2-1',
                   opscode_path='/ubuntu/12.04/x86_64/chef_11.8.2-1.ubuntu.12.04_amd64.deb')

class TestRelease(object):
    def test_codename(self, release1, release2):
        assert release1.codename == 'squeeze'
        assert release2.codename == 'precise'

    def test_component(self, release1, release2):
        assert release1.component == 'chef-10'
        assert release2.component == 'chef-11'

    def test_pool_path(self, release1, release2):
        assert release1.pool_path == 'pool/debian-6/chef_10.12.0-1.debian.6.0.5_amd64.deb'
        assert release2.pool_path == 'pool/ubuntu-12.04/chef_11.8.2-1.ubuntu.12.04_amd64.deb'

    def test_to_json(self, release1, release2):
        assert release1.to_json() == {
            'platform': 'debian',
            'platform_version': '6',
            'arch': 'x86_64',
            'version': '10.12.0-1',
            'opscode_path': '/debian/6/x86_64/chef_10.12.0-1.debian.6.0.5_amd64.deb',
        }

def test_allowed_versions():
    assert ALLOWED_VERSIONS.match('1.2.3')
    assert ALLOWED_VERSIONS.match('10.30.2')
    assert ALLOWED_VERSIONS.match('11.18.4')
    assert ALLOWED_VERSIONS.match('1.2.3-1')
    assert not ALLOWED_VERSIONS.match('1.2.3.rc.1-1')
    assert not ALLOWED_VERSIONS.match('1.2.3.beta.2-1')
    assert not ALLOWED_VERSIONS.match('1.2')
