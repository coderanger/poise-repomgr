poise-repomgr
=============

Repomgr is a small Heroku application to monitor the Chef Omnitruck API and add
the packages to apt repositories for use with normal Debian-style packaging
tools.

Deploying
---------

To deploy on Heroku, repomgr requires a few config variables:

* `AWS_ACCESS_KEY_ID` – AWS access key with write permissions for the requested bucket.
* `AWS_SECRET_ACCESS_KEY` – AWS secret key for the above access key.
* `BUILDPACK_URL` – Must be set to `https://github.com/ddollar/heroku-buildpack-multi.git`.
* `SIGNING_KEY` – ASCII-armored export of the GPG secret key to use for package signing.
* `STORAGE_URI` – A depot-compatible storage URI to use for repositories.

Using Packages
--------------

To enable the repositories:

```bash
$ sudo apt-add-repository 'http://apt.poise.io chef-11'
$ sudo apt-key adv --keyserver hkp://pgp.mit.edu --recv 594F6D7656399B5C
$ sudo apt-get update
$ sudo apt-get install chef
```

There is also a `chef-10` component available if you want Chef 10.x releases.
