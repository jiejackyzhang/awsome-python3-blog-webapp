#!/usr/bin/env python3
# -*- coding: utf-8 -*-


'''
async web application
'''

__author__ = 'Jacky Zhang'

import logging
logging.basicConfig(level=logging.INFO)

import asyncio, os, json, time
from datetime import datetime

from aiohttp import web
from jinja2 import Environment, FileSystemLoader

from config import configs

import orm
from coroweb import add_routes, add_static
from handlers import cookie2user, COOKIE_NAME

'''
# a simple demo of aiohttp
def index(request):
    return web.Response(body=b'<h1>Blog Web App</h1>')

async def init(loop):
	app = web.Application(loop=loop)
	app.router.add_route('GET', '/', index)
	srv = await loop.create_server(app.make_handler(), '127.0.0.1', 9000)
	logging.info('server started at http://127.0.0.1:9000...')
	return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()
'''

def init_jinja2(app, **kw):
	logging.info('init jinja2...')
	options = dict(
			autoescape = kw.get('autoescape', True),
			block_start_string = kw.get('block_start_string', '{%'),
			block_end_string = kw.get('block_end_string', '%}'),
			variable_start_string = kw.get('variable_start_string', '{{'),
			variable_end_string = kw.get('variable_end_string', '}}'),
			auto_reload = kw.get('auto_reload', True)
		)
	# get path of template file
	path = kw.get('path', None)
	if path is None:
		# if None, then templates fold under current file directory
		path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
	logging.info('set jinja2 template path: %s' % path)
	env = Environment(loader=FileSystemLoader(path), **options)
	filters = kw.get('filters', None)
	if filters is not None:
		for name, f in filters.items():
			env.filters[name] = f
	app['__templating__'] = env

# ------------- middlewares ----------------------------

async def logger_factory(app, handler):
	async def logger(request):
		logging.info('Request: %s %s' % (request.method, request.path))
		return (await handler(request))
	return logger

async def auth_factory(app, handler):
	async def auth(request):
		logging.info('check user: %s %s' % (request.method, request.path))
		request.__user__ = None
		cookie_str = request.cookies.get(COOKIE_NAME)
		if cookie_str:
			user = await cookie2user(cookie_str)
			if user:
				logging.info('set current user: %s' % user.email)
				request.__user__ = user
		if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
			return web.HTTPFound('/signin')
		return (await handler(request))
	return auth

async def data_factory(app, handler):
	async def parse_data(request):
		if request.method == 'POST':
			if request.content_type.startswith('application/json'):
				request.__data__ = await request.json()
				logging.info('request json: %s' % str(request.__data__))
			elif request.content_type.startswith('application/x-www-form-urlencoded'):
				request.__data__ = await request.post()
				logging.info('request form: %s' % str(request.__data__))
		return (await handler(request))
	return parse_data

async def response_factory(app, handler):
	# transfer return value to web.Response before return
	# to satisfy requirements of aiohttp
	async def response(request):
		logging.info('Response handler...')
		r = await handler(request)
		if isinstance(r, web.StreamResponse):
			return r
		if isinstance(r, bytes):
			resp = web.Response(body=r)
			resp.content_type = 'application/octet-stream'
			return resp
		if isinstance(r, str):
			if r.startswith('redirect:'):
				return web.HTTPFound(r[9:])
			resp = web.Response(body = r.encode('utf-8'))
			resp.content_type = 'text/html;charset=utf-8'
			return resp
		if isinstance(r, dict):
			template = r.get('__template__')
			if template is None:
				# if not, return as json
				resp = web.Response(body=json.dumps(r, ensure_ascii=False, default=lambda o: o.__dict__).encode('utf-8'))
				resp.content_type = 'application/json'
				return resp
			else:
				# set __base__.html according to user
				r['__user__'] = request.__user__
				resp = web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
				resp.content_type = 'text/html;charset=utf-8'
				return resp
		if isinstance(r, int) and r >= 100 and r < 600:
			return web.Response(r)
		if isinstance(r, tuple) and len(r) == 2:
			status_code, description = r
			if isinstance(status_code. int) and status_code >= 100 and status_code < 600:
				resp = web.Response(status=status_code, text=str(description))
				resp.content_type = 'text/plain;charset=utf-8'
				return resp
	return response

# ----------------------------------------------------

def datetime_filter(t):
	delta = int(time.time() - t)
	if delta < 60:
		return '1 min ago'
	elif delta < 3600:
		return '%s mins ago' % (delta // 60)
	elif delta < 3600 * 2:
		return '1 hour ago'
	elif delta < 86400:
		return '%s hours ago' % (delta // 3600)
	elif delta < 86400 * 2:
		return '1 day ago'
	elif delta < 604800:
		return '%s days ago' % (delta // 86400)
	else:
		dt = datetime.fromtimestamp(t)
		return '%s-%s-%s' % (dt.year, dt.month, dt.day)

async def init(loop):
	await orm.create_pool(loop=loop, **configs.db)
	app = web.Application(loop=loop, middlewares=[logger_factory, auth_factory, response_factory])
	init_jinja2(app, filters=dict(datetime=datetime_filter))
	# add url handle func, 'handlers' is the module name
	add_routes(app, 'handlers')
	# add path of static files
	add_static(app)
	# start server
	srv_host = '127.0.0.1'
	srv_port = 9000
	srv = await loop.create_server(app.make_handler(), host=srv_host, port=srv_port)
	logging.info('server started at http://%s:%d ........' % (srv_host, srv_port)) 
	return srv

loop = asyncio.get_event_loop()
loop.run_until_complete(init(loop))
loop.run_forever()