#!/usr/bin/env python3
# -*- coding: utf-8 -*-


'''
test sql
'''

__author__ = 'Jacky Zhang'

import orm, asyncio
from models import User, Blog, Comment

async def test(loop):
	
	await orm.create_pool(loop=loop, user='root', password='password', database='blog')
	
	u = User(name='Test', email='test@example.com', passwd='1234567890', admin=True, image='about:blank')

	await u.save()

loop = asyncio.get_event_loop()
loop.run_until_complete(test(loop))
loop.close()