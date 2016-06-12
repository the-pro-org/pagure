#!/usr/bin/env python

import os
from datetime import datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

if 'PAGURE_CONFIG' not in os.environ \
        and os.path.exists('/etc/pagure/pagure.cfg'):
    print 'Using configuration file `/etc/pagure/pagure.cfg`'
    os.environ['PAGURE_CONFIG'] = '/etc/pagure/pagure.cfg'

import pagure
from pagure import SESSION
from pagure.lib import model


current_time = datetime.utcnow()
day_diff_for_mail = [5, 3, 1]
email_dates = [email_day.date() for email_day in [current_time + timedelta(days=i)\
        for i in day_diff_for_mail]]

tokens = SESSION.query(model.Token).all()

for token in tokens:
    if token.expiration.date() in email_dates:
        user = token.user
        user_email = user.default_email
        project = token.project
        days_left = token.expiration.day - datetime.utcnow().day
        subject = 'Pagure API key expiration date is near!'
        text = '''Hi %s, \nYour Pagure API key for the project %s will expire
in %s day(s). Please get a new key for non-interrupted service. \n
Thanks, \nYour Pagure Admin. ''' % (user.fullname, project.name, days_left)
        msg = pagure.lib.notify.send_email(text, subject, user_email)
        print 'Sent mail to %s' % user.fullname

print 'Done'
