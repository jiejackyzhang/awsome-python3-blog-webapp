#!/usr/bin/env python3
# -*- coding: utf-8 -*-

'''
Web framework.
'''

__author__ = 'Jacky Zhang'

import asyncio, os, inspect, logging, functools
from aiohttp import web
from urllib import parse
from apis import APIError

# get and post are decorators, 
# in order to add attributes __method__ and __route__

def get(path):
	'''
	define decorator @get('/path')
	'''
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kw):
			return func(*args, **kw)
		wrapper.__method__ = 'GET'
		wrapper.__route__ = path
		return wrapper
	return decorator

def post(path):
	'''
	define decorator @post('/path')
	'''
	def decorator(func):
		@functools.wraps(func)
		def wrapper(*args, **kw):
			return func(*args, **kw)
		wrapper.__method__ = 'POST'
		wrapper.__route__ = path
		return wrapper
	return decorator

# ------ use inspect.signature method to get attrs of a function
# inspect.Parameter.kind has five types:
# POSITIONAL_ONLY: Value must be supplied as a positional argument
# POSITIONAL_OR_KEYWORD： Value may be supplied as either a keyword or positional argument 
# VAR_POSITIONAL： corresponds to a *args parameter
# KEYWORD_ONLY： Value must be supplied as a keyword argument
# VAR_KEYWORD: corresponds to a **kw parameter

def has_request_arg(fn):
	# return True if has request arg (the last positional arg)
	sig = inspect.signature(fn)
	params = sig.parameters
	found = False
	for name, param in params.items():
		if name == 'request':
			found = True
			continue
		if found and (param.kind != inspect.Parameter.VAR_POSITIONAL and param.kind != inspect.Parameter.KEYWORD_ONLY and param.kind != inspect.Parameter.VAR_KEYWORD):
			raise ValueError('request parameter must be the last named parameter in function: %s%s' % (fn.__name__, str(sig)))
	return found

def has_var_kw_arg(fn):
	# return True if has VAR_KEYWORD arg
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.VAR_KEYWORD:
			return True

def has_named_kw_args(fn):
	# return True if has KEYWORD arg
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			return True

def get_named_kw_args(fn):
	# get all keys if fn has keyword args
	args = []
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY:
			args.append(name)
	return tuple(args)

def get_required_kw_args(fn):
	# get keys if the keyword arg has no default value
	args = []
	params = inspect.signature(fn).parameters
	for name, param in params.items():
		if param.kind == inspect.Parameter.KEYWORD_ONLY and param.default == inspect.Parameter.empty:
			args.append(name)
	return tuple(args)

class RequestHandler(object):
	'''
	RequestHandler目的就是从URL函数中分析其需要接收的参数，从request中获取必要的参数，调用URL函数，然后把结果转换为web.Response对象
	RequestHandler是一个类，由于定义了__call__()方法，因此可以将其实例视为函数
	'''
	def __init__(self, app, fn):
		self._app = app
		self._func = fn
		self._has_request_arg = has_request_arg(fn)
		self._has_var_kw_arg = has_var_kw_arg(fn)
		self._has_named_kw_args = has_named_kw_args(fn)
		self._named_kw_args = get_named_kw_args(fn)
		self._required_kw_args = get_required_kw_args(fn)
		
	async def __call__(self, request):
		kw = None # store args
		if self._has_var_kw_arg or self._has_named_kw_args or self._has_request_arg:
			if request.method == 'POST':
				if not request.content_type:
					return web.HTTPBadRequest('Missing Content-Type.')
				ct = request.content_type.lower()
				if ct.startswith('application/json'):
					params = await request.json()
					if not isinstance(params, dict):
						return web.HTTPBadRequest('JSON body must be object.')
					kw = params
				elif ct.startswith('application/x-www-form-urlencoded') or ct.startswith('multipart/form-data'):
					params = await request.post()
					kw = dict(**params)
				else:
					return web.HTTPBadRequest('Unsupported Content-Type: %s' % request.content_type)
			if request.method == 'GET':
				qs = request.query_string
				if qs:
					kw = dict()
					for k, v in parse.parse_qs(qs, True).items():
						kw[k] = v[0]
						# 解析url中?后面的键值对内容保存到request_content
						'''
						qs = 'first=f,s&second=s'
						parse.parse_qs(qs, True).items()	
						>>> dict([('first', ['f,s']), ('second', ['s'])])
						'''
		if kw is None:
			# if get no args from request or handler func has no args
			kw = dict(**request.match_info)
		else:
			if not self._has_var_kw_arg and self._has_named_kw_args:
				# remove all unnamed kw
				copy = dict()
				for name in self._named_kw_args:
					if name in kw:
						copy[name] = kw[name]
				kw = copy
			# check named arg
			for k, v in request.match_info.items():
				if k in kw:
					logging.warning('Duplicate arg name in named arg and kw args: %s' % k)
				kw[k] = v
		if self._has_request_arg:
			kw['request'] = request
		# check required kw
		if self._required_kw_args:
			for name in self._required_kw_args:
				if not name in kw:
					return web.HTTPBadRequest('Missing argument: %s' % name)
		logging.info('call with args: %s' % str(kw))
		try:
			r = await self._func(**kw)
			return r
		except APIError as e:
			return dict(error=e.error, data=e.data, message=e.message)

def add_static(app):
	# add path of static file like CSS
	path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
	app.router.add_static('/static/', path)
	logging.info('add static %s => %s' % ('/static/', path))

def add_route(app, fn):
	method = getattr(fn, '__method__', None)
	path = getattr(fn, '__route__', None)
	if method is None or path is None:
		raise ValueError('@get or @post not defined in %s.' % str(fn))
	if not asyncio.iscoroutinefunction(fn) and not inspect.isgeneratorfunction(fn):
		#用asyncio.coroutine装饰函数fn
		fn = asyncio.coroutine(fn)
	logging.info('add route %s %s => %s(%s)' % (method, path, fn.__name__, ', '.join(inspect.signature(fn).parameters.keys())))
	# url handler: RequestHandler.__call__
	app.router.add_route(method, path, RequestHandler(app, fn))

def add_routes(app, module_name):
	# module_name format: 'handlers.index'
	n = module_name.rfind('.')
	if n == (-1):
		'''
		__import__ 作用同import语句，但__import__是一个函数，并且只接收字符串作为参数, 
		其实import语句就是调用这个函数进行导入工作的, 其返回值是对应导入模块的引用
		没有'.',则传入的是module名, __import__(module)其实就是 import module
		'''		
		mod = __import__(module_name, globals(), locals())
	else:
		'''		
		__import__('os',globals(),locals(),['path','pip']) ,等价于from os import path, pip
		'''
		name = module_name[n+1:]
		mod = getattr(__import__(module_name[:n], globals(), locals(), [name]), name)
	for attr in dir(mod):
		# dir函数的作用是列出对象的所有特性（以及模块的所有函数、类、变量等）
		if attr.startswith('_'):
			continue
		fn = getattr(mod, attr)
		if callable(fn):
			method = getattr(fn, '__method__', None)
			path = getattr(fn, '__route__', None)
			if method and path:
				add_route(app, fn)
