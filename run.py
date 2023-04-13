#!/usr/bin/env python3
# -*- coding:utf-8 -*-

import os

from flask_migrate import Migrate
from flask_minify import Minify
from sys import exit

from backend.api.tasks import scheduler, update_playlists, map_new_tvh_services, update_epgs, rebuild_custom_epg, \
    update_tvh_muxes
from lib.config import config_dict
from backend import create_app, db

# WARNING: Don't run with debug turned on in production!
DEBUG = (os.getenv('FLASK_DEBUG', 'False').capitalize() == 'True')

# The configuration
get_config_mode = 'Debug' if DEBUG else 'Production'

try:
    # Load the configuration using the default values
    app_config = config_dict[get_config_mode.capitalize()]
except KeyError:
    exit('Error: Invalid <config_mode>. Expected values [Debug, Production] ')

app = create_app(app_config)
Migrate(app, db)

if not DEBUG:
    Minify(app=app, html=True, js=False, cssless=False)

if DEBUG:
    app.logger.info('DEBUG       = ' + str(DEBUG))
    app.logger.info('DBMS        = ' + app_config.SQLALCHEMY_DATABASE_URI)
    app.logger.info('ASSETS_ROOT = ' + app_config.ASSETS_ROOT)


@scheduler.task('interval', id='do_5_mins', minutes=5, misfire_grace_time=60)
def every_5_mins():
    with app.app_context():
        map_new_tvh_services(app)


@scheduler.task('interval', id='do_60_mins', minutes=60, misfire_grace_time=300)
def every_60_mins():
    with app.app_context():
        update_tvh_muxes(app)


@scheduler.task('interval', id='do_12_hours', hours=12, misfire_grace_time=900)
def every_12_hours():
    with app.app_context():
        update_playlists(app)
        update_epgs(app)


@scheduler.task('interval', id='do_24_hours', hours=24, misfire_grace_time=900)
def every_24_hours():
    with app.app_context():
        rebuild_custom_epg(app)


if __name__ == "__main__":
    app.run()