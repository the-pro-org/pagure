 (c) 2015-2016 - Copyright Red Hat Inc
            blacklist=pagure.APP.config['BLACKLISTED_GROUPS'],
        output = self.app.get('/foo/forks', follow_redirects=True)
        output = self.app.get('/test/forks', follow_redirects=True)
        output = self.app.get('/foo/c/bar')
        output = self.app.get('/test/c/bar')
        output = self.app.get('/test/c/bar')
        output = self.app.get('/test/c/%s' % commit.oid.hex)
        # View first commit - with the old URL scheme disabled - default
        output = self.app.get(
            '/test/%s' % commit.oid.hex, follow_redirects=True)
        self.assertEqual(output.status_code, 404)
        self.assertIn('<p>Project not found</p>', output.data)

        output = self.app.get('/test/c/%s' % commit.oid.hex)
        output = self.app.get('/test/c/%s' % commit.oid.hex)
        output = self.app.get(
            '/fork/pingou/test3/c/%s' % commit.oid.hex)
        # Try the old URL scheme with a short hash
        output = self.app.get(
            '/fork/pingou/test3/%s' % commit.oid.hex[:10],
            follow_redirects=True)
        self.assertEqual(output.status_code, 404)
        self.assertIn('<p>Project not found</p>', output.data)


        output = self.app.get('/foo/c/bar.patch')
        output = self.app.get('/test/c/bar.patch')
        output = self.app.get('/test/c/bar.patch')
        output = self.app.get('/test/c/%s.patch' % commit.oid.hex)
        output = self.app.get('/test/c/%s.patch' % commit.oid.hex)
        output = self.app.get('/test/c/%s.patch' % commit.oid.hex)
        output = self.app.get(
            '/fork/pingou/test3/c/%s.patch' % commit.oid.hex)
        output = self.app.post('/foo/b/master/delete')
            output = self.app.post('/foo/b/master/delete')
            output = self.app.post('/test/b/master/delete')
            output = self.app.post('/test/b/master/delete')
            output = self.app.post('/test/b/bar/delete')
            output = self.app.get('/test')
            output = self.app.post('/test/b/foo/delete', follow_redirects=True)
            output = self.app.get('/test')
            output = self.app.post('/test/b/feature/foo/delete', follow_redirects=True)