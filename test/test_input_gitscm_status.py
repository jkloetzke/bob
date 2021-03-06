# Bob build tool
# Copyright (C) 2016 BobBuildTool team
#
# SPDX-License-Identifier: GPL-3.0-or-later

from unittest import TestCase

import os
import subprocess
import tempfile

from bob.scm import GitScm, ScmTaint
from bob.utils import removePath

class TestGitScmStatus(TestCase):
    repodir = ""
    repodir_local = ""

    def statusGitScm(self, spec = {}):
        s = { 'scm' : "git", 'url' : self.repodir, 'recipe' : "foo.yaml#0",
            '__source' : "Recipe foo" }
        s.update(spec)
        return GitScm(s).status(self.repodir_local)

    def callGit(self, *arg, **kwargs):
        try:
            subprocess.check_output(*arg, shell=True, universal_newlines=True, stderr=subprocess.STDOUT, **kwargs)
        except subprocess.CalledProcessError as e:
            self.fail("git error: '{}' '{}'".format(arg, e.output))

    def tearDown(self):
        removePath(self.repodir)
        removePath(self.repodir_local)

    def setUp(self):
        self.repodir = tempfile.mkdtemp()
        self.repodir_local = tempfile.mkdtemp()

        self.callGit('git init', cwd=self.repodir)

        # setup user name and email for travis
        self.callGit('git config user.email "bob@bob.bob"', cwd=self.repodir)
        self.callGit('git config user.name test', cwd=self.repodir)

        f = open(os.path.join(self.repodir, "test.txt"), "w")
        f.write("hello world")
        f.close()
        self.callGit('git add test.txt', cwd=self.repodir)
        self.callGit('git commit -m "first commit"', cwd=self.repodir)

        # create a regular and a orphaned tag (one that is on no branch)
        self.callGit("git tag -a -m '1.0' v1.0", cwd=self.repodir)
        self.callGit("git checkout --detach", cwd=self.repodir)
        with open(os.path.join(self.repodir, "test.txt"), "w") as f:
            f.write("foo")
        self.callGit('git commit -a -m "second commit"', cwd=self.repodir)
        self.callGit("git tag -a -m '1.1' v1.1", cwd=self.repodir)

        # clone repository
        self.callGit('git init .', cwd=self.repodir_local)
        self.callGit('git remote add origin ' + self.repodir, cwd=self.repodir_local)
        self.callGit('git fetch origin', cwd=self.repodir_local)
        self.callGit('git checkout master', cwd=self.repodir_local)

        # setup user name and email for travis
        self.callGit('git config user.email "bob@bob.bob"', cwd=self.repodir_local)
        self.callGit('git config user.name test', cwd=self.repodir_local)

    def testBranch(self):
        s = self.statusGitScm({ 'branch' : 'anybranch' })
        self.assertEqual(s.flags, {ScmTaint.switched})
        self.assertTrue(s.dirty)

    def testClean(self):
        s = self.statusGitScm()
        self.assertEqual(s.flags, set())
        self.assertTrue(s.clean)

    def testCommit(self):
        s = self.statusGitScm({ 'commit' : '0123456789012345678901234567890123456789' })
        self.assertEqual(s.flags, {ScmTaint.switched})
        self.assertTrue(s.dirty)

    def testNonExisting(self):
        removePath(self.repodir_local)
        s = self.statusGitScm()
        self.assertEqual(s.flags, {ScmTaint.error})
        self.assertTrue(s.error)

    def testModified(self):
        with open(os.path.join(self.repodir_local, "test.txt"), "w") as f:
            f.write("test modified")
        s = self.statusGitScm()
        self.assertEqual(s.flags, {ScmTaint.modified})
        self.assertTrue(s.dirty)

    def testTag(self):
        s = self.statusGitScm({ 'tag' : 'v0.1' })
        self.assertEqual(s.flags, {ScmTaint.switched})
        self.assertTrue(s.dirty)

    def testUnpushedMain(self):
        with open(os.path.join(self.repodir_local, "test.txt"), "w") as f:
            f.write("test modified")
        self.callGit('git commit -a -m "modified"', cwd=self.repodir_local)

        s = self.statusGitScm()
        self.assertEqual(s.flags, {ScmTaint.unpushed_main})
        self.assertTrue(s.dirty)

    def testUnpushedLocal(self):
        self.callGit('git checkout -b unrelated', cwd=self.repodir_local)
        with open(os.path.join(self.repodir_local, "test.txt"), "w") as f:
            f.write("test modified")
        self.callGit('git commit -a -m "modified"', cwd=self.repodir_local)
        self.callGit('git checkout master', cwd=self.repodir_local)

        s = self.statusGitScm()
        self.assertEqual(s.flags, {ScmTaint.unpushed_local})
        self.assertFalse(s.dirty)

    def testUnpushedBoth(self):
        self.callGit('git checkout -b unrelated', cwd=self.repodir_local)
        with open(os.path.join(self.repodir_local, "test.txt"), "w") as f:
            f.write("unrelated modified")
        self.callGit('git commit -a -m whatever', cwd=self.repodir_local)
        self.callGit('git checkout master', cwd=self.repodir_local)
        with open(os.path.join(self.repodir_local, "test.txt"), "w") as f:
            f.write("test modified")
        self.callGit('git commit -a -m "modified"', cwd=self.repodir_local)

        s = self.statusGitScm()
        self.assertEqual(s.flags, {ScmTaint.unpushed_main, ScmTaint.unpushed_local})
        self.assertTrue(s.dirty)

    def testUrl(self):
        s = self.statusGitScm({ 'url' : 'anywhere' })
        self.assertEqual(s.flags, {ScmTaint.switched})
        self.assertTrue(s.dirty)

    def testOrphanedOk(self):
        self.callGit('git fetch origin tag v1.1', cwd=self.repodir_local)
        self.callGit('git checkout tags/v1.1', cwd=self.repodir_local)
        s = self.statusGitScm({ 'tag' : 'v1.1' })
        self.assertEqual(s.flags, set())
