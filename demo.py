#!/usr/bin/env python

import os

import tornado.options
from tornado.options import options
from tornado.ioloop import IOLoop
from tornado.httpserver import HTTPServer
from tornado import web
from tornado import gen

from third import DoubanMixin
from third import RenrenGraphMixin, RenrenRestMixin
from third import WeiboMixin

_app_cache = {}

host = 'http://dev.example.com'

class InstanceCache(object):
    def clear(self):
        global _app_cache

        for key, value in _app_cache.iteritems():
            expiry = value[1]
            if expiry and time() > expiry:
                del _app_cache[key]

    def flush_all(self):
        global _app_cache

        _app_cache = {}

    def set(self, key, value, seconds=0):
        global _app_cache

        if seconds < 0:
            seconds = 0

        _app_cache[key] = (value, time() + seconds if seconds else 0)

    def get(self, key):
        global _app_cache

        value = _app_cache.get(key, None)
        if value:
            expiry = value[1]
            if expiry and time() > expiry:
                del _app_cache[key]
                return None
            else:
                return value[0]
        return None

    def delete(self, key):
        global _app_cache
    
        if _app_cache.has_key(key):
            del _app_cache[key]
        return None

class BaseHandler(web.RequestHandler):
    @property
    def cache(self):
        return self.application.cache

class DoubanHandler(BaseHandler, DoubanMixin):
    @web.asynchronous
    def get(self):
        if self.cache.get('douban'):
            return self._write_html()

        if self.get_argument("oauth_token", None):
            self.get_authenticated_user(self.async_callback(self._on_auth))
            return
        self.authorize_redirect(host + '/douban')
    
    @web.asynchronous
    def post(self):
        user = self.cache.get('douban')
        if not user:
            return self.authorize_redirect(host + '/douban')

        content = self.get_argument('content')
        self.douban_saying(self.async_callback(self._on_saying),
                access_token=user["access_token"], content=content)

    def _on_auth(self, user):
        if not user:
            raise web.HTTPError(500, "Douban auth failed")
        self.cache.set('douban', user)
        self._write_html()

    def _on_saying(self, xml):
        if not xml:
            raise tornado.web.HTTPError(500, 'Douban saying failed')
        self.write(xml)
        self.finish()

    def _write_html(self):
        html = '''
        <form method="post">
        <textarea name="content"></textarea><input type="submit" />
        </form>
        '''
        self.write(html)
        self.finish()


class RenrenHandler(BaseHandler, RenrenGraphMixin):
    @web.asynchronous
    @gen.engine
    def get(self):
        renren = self.cache.get('renren')
        if renren:
            self.write(renren)
            self.finish()
            return

        self.get_authenticated_user(
            redirect_uri=host+'/renren',
            callback=(yield gen.Callback('RenrenHandler.get')))
        user = yield gen.Wait('RenrenHandler.get')
        if not user:
            raise web.HTTPError(500, "Renren auth failed")
        self.cache.set('renren', user)
        self.write(user)
        self.finish()


class WeiboHandler(BaseHandler, WeiboMixin):
    @tornado.web.asynchronous
    def get(self):
        if self.get_argument("code", False):
            self.get_authenticated_user(
                redirect_uri='http://127.0.0.1:8000/weibo',
                client_id=self.settings["weibo_api_key"],
                client_secret=self.settings["weibo_secret"],
                code=self.get_argument("code"),
                callback=self.async_callback(self._on_login))
            return
        self.authorize_redirect(redirect_uri='http://127.0.0.1:8000/weibo',
                                client_id=self.settings["weibo_api_key"],
                                extra_params={"response_type": "code"})

    def _on_login(self, user):
        for k, v in user.iteritems():
            self.write("%s : %s<br/>" % (k, v))
        self.finish()


class Application(web.Application):
    def __init__(self):
        handlers = [
            ('/douban', DoubanHandler),
            ('/renren', RenrenHandler),
            ('/weibo', WeiboHandler),
        ]
        settings = dict(
            debug = True,
            autoescape = None,
            cookie_secret = 'secret',
            xsrf_cookies = False,

            douban_consumer_key = '',
            douban_consumer_secret = '',
            renren_client_id = 'fee11992a4ac4caabfca7800d233f814',
            renren_client_secret = 'a617e78710454b12aab68576382e8e14',
            weibo_api_key = '',
            weibo_secret = '',
        )
        web.Application.__init__(self, handlers, **settings)
        Application.cache = InstanceCache()


def run_server():
    tornado.options.parse_command_line()
    server = HTTPServer(Application(), xheaders=True)
    server.bind(8000)
    server.start(1)
    IOLoop.instance().start()

if __name__ == "__main__":
    run_server()
