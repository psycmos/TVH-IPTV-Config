#!/usr/bin/env python3
# -*- coding:utf-8 -*-

from sqlalchemy.orm import joinedload
from sqlalchemy import and_
from backend import db
from backend.models import Channel, ChannelTag, Epg, ChannelSource, Playlist
from backend.playlists import read_stream_data_from_playlist
from backend.tvheadend.tvh_requests import get_tvh
from lib.playlist import read_data_from_playlist_cache, generate_iptv_url


def read_config_all_channels():
    return_list = []
    for result in db.session.query(Channel) \
            .options(joinedload(Channel.tags), joinedload(Channel.sources).subqueryload(ChannelSource.playlist)) \
            .all():
        tags = []
        for tag in result.tags:
            tags.append(tag.name)
        sources = []
        for source in result.sources:
            sources.append({
                'playlist_id':   source.playlist_id,
                'playlist_name': source.playlist.name,
                'priority':      1,
                'stream_name':   source.playlist_stream_name,
            })
        return_list.append({
            'id':       result.id,
            'enabled':  result.enabled,
            'name':     result.name,
            'logo_url': result.logo_url,
            'number':   result.number,
            'tags':     tags,
            'guide':    {
                'epg_id':     result.guide_id,
                'epg_name':   result.guide_name,
                'channel_id': result.guide_channel_id,
            },
            'sources':  sources,
        })
    return return_list


def read_config_one_channel(channel_id):
    return_item = {}
    result = db.session.query(Channel) \
        .options(joinedload(Channel.tags), joinedload(Channel.sources).subqueryload(ChannelSource.playlist)) \
        .filter(Channel.id == channel_id) \
        .one()
    if result:
        tags = []
        for tag in result.tags:
            tags.append(tag.name)
        sources = []
        for source in result.sources:
            sources.append({
                'playlist_id':   source.playlist_id,
                'playlist_name': source.playlist.name,
                'priority':      1,
                'stream_name':   source.playlist_stream_name,
            })
        return_item = {
            'id':       result.id,
            'enabled':  result.enabled,
            'name':     result.name,
            'logo_url': result.logo_url,
            'number':   result.number,
            'tags':     tags,
            'guide':    {
                'epg_id':     result.guide_id,
                'epg_name':   result.guide_name,
                'channel_id': result.guide_channel_id,
            },
            'sources':  sources,
        }
    return return_item


def add_new_channel(config, data):
    channel = Channel(
        enabled=data.get('enabled'),
        name=data.get('name'),
        logo_url=data.get('logo_url'),
        number=data.get('number'),
    )
    # Add tags
    for tag_name in data.get('tags', []):
        channel_tag = db.session.query(ChannelTag).filter(ChannelTag.name == tag_name).one_or_none()
        if not channel_tag:
            channel_tag = ChannelTag(name=tag_name)
            db.session.add(channel_tag)
        channel.tags.append(channel_tag)

    # Programme Guide
    guide_info = data.get('guide', {})
    if guide_info.get('epg_id'):
        channel_guide_source = db.session.query(Epg).filter(Epg.id == guide_info['epg_id']).one()
        channel.guide_id = channel_guide_source.id
        channel.guide_name = guide_info['epg_name']
        channel.guide_channel_id = guide_info['channel_id']

    # Sources
    new_sources = []
    for source_info in data.get('sources', []):
        playlist_info = db.session.query(Playlist).filter(Playlist.id == source_info['playlist_id']).one()
        streams = read_stream_data_from_playlist(config, playlist_info.id)
        stream_data = streams.get(source_info['stream_name'])
        channel_source = ChannelSource(
            playlist_id=playlist_info.id,
            playlist_stream_name=source_info['stream_name'],
            playlist_stream_url=stream_data['url'],
        )
        new_sources.append(channel_source)
    if new_sources:
        channel.sources.clear()
        channel.sources = new_sources

    # Add new row and commit
    db.session.add(channel)
    db.session.commit()


def update_channel(config, channel_id, data):
    channel = db.session.query(Channel).where(Channel.id == channel_id).one()
    channel.enabled = data.get('enabled')
    channel.name = data.get('name')
    channel.logo_url = data.get('logo_url')
    channel.number = data.get('number')

    # Category Tags
    # -- Remove existing tags
    channel.tags.clear()
    # -- Add tags
    new_tags = []
    for tag_name in data.get('tags', []):
        channel_tag = db.session.query(ChannelTag).filter(ChannelTag.name == tag_name).one_or_none()
        if not channel_tag:
            channel_tag = ChannelTag(name=tag_name)
            db.session.add(channel_tag)
        new_tags.append(channel_tag)
    channel.tags.clear()
    channel.tags = new_tags

    # Programme Guide
    guide_info = data.get('guide', {})
    if guide_info.get('epg_id'):
        channel_guide_source = db.session.query(Epg).filter(Epg.id == guide_info['epg_id']).one()
        channel.guide_id = channel_guide_source.id
        channel.guide_name = guide_info['epg_name']
        channel.guide_channel_id = guide_info['channel_id']

    # Sources
    new_source_ids = []
    new_sources = []
    for source_info in data.get('sources', []):
        channel_source = db.session.query(ChannelSource) \
            .filter(and_(ChannelSource.channel_id == channel.id,
                         ChannelSource.playlist_id == source_info['playlist_id'],
                         ChannelSource.playlist_stream_name == source_info['stream_name']
                         )) \
            .one_or_none()
        if channel_source:
            new_source_ids.append(channel_source.id)
        if not channel_source:
            playlist_info = db.session.query(Playlist).filter(Playlist.id == source_info['playlist_id']).one()
            streams = read_stream_data_from_playlist(config, playlist_info.id)
            stream_data = streams.get(source_info['stream_name'])
            channel_source = ChannelSource(
                playlist_id=playlist_info.id,
                playlist_stream_name=source_info['stream_name'],
                playlist_stream_url=stream_data['url'],
            )
        new_sources.append(channel_source)
    # Remove all old entries in the channel_sources table
    current_sources = db.session.query(ChannelSource).filter_by(channel_id=channel.id)
    for source in current_sources:
        if source.id not in new_source_ids:
            if source.tvh_uuid:
                # Delete mux from TVH
                delete_channel_muxes(config, source.tvh_uuid)
            db.session.delete(source)
    if new_sources:
        channel.sources.clear()
        channel.sources = new_sources

    # Commit
    db.session.commit()


def delete_channel(config, channel_id):
    channel = db.session.query(Channel).where(Channel.id == channel_id).one()
    # Remove all source entries in the channel_sources table
    current_sources = db.session.query(ChannelSource).filter_by(channel_id=channel.id)
    for source in current_sources:
        if source.tvh_uuid:
            # Delete mux from TVH
            delete_channel_muxes(config, source.tvh_uuid)
        db.session.delete(source)
    # Remove from DB
    db.session.delete(channel)
    db.session.commit()


def publish_channel_muxes(config):
    tvh = get_tvh(config)
    # TODO: Add support for settings priority
    # Loop over configured channels
    existing_uuids = []
    results = db.session.query(Channel) \
        .options(joinedload(Channel.tags), joinedload(Channel.sources).subqueryload(ChannelSource.playlist)) \
        .all()
    for result in results:
        if result.enabled:
            print(f"Configuring MUX for channel '{result.name}'")
            # Create/update a network in TVH for each enabled playlist line
            for source in result.sources:
                playlist_entries = read_data_from_playlist_cache(config, source.playlist_id)
                if not playlist_entries:
                    print("No playlist is configured")
                    continue
                # playlist_info = settings['playlists'][source['playlist_id']]
                # Write playlist to TVH Network
                net_uuid = source.playlist.tvh_uuid
                if not net_uuid:
                    # Show error
                    print("Playlist is not configured on TVH")
                    continue
                # Check if MUX exists with a matching UUID and create it if not
                mux_uuid = source.tvh_uuid
                run_mux_scan = False
                if mux_uuid:
                    found = False
                    for mux in tvh.list_all_muxes():
                        if mux.get('uuid') == mux_uuid:
                            found = True
                    if not found:
                        mux_uuid = None
                if not mux_uuid:
                    # No mux exists, create one
                    mux_uuid = tvh.network_mux_create(net_uuid)
                    run_mux_scan = True
                # Update mux
                service_name = f"{source.playlist.name} - {source.playlist_stream_name}"
                iptv_url = generate_iptv_url(
                    config,
                    url=playlist_entries[source.playlist_stream_name]['url'],
                    service_name=service_name,
                )
                iptv_icon_url = playlist_entries \
                    .get(source.playlist_stream_name, {}) \
                    .get('attributes', {}) \
                    .get('tvg-logo', '')
                mux_conf = {
                    'enabled':        1,
                    'uuid':           mux_uuid,
                    'iptv_url':       iptv_url,
                    'iptv_icon':      iptv_icon_url,
                    'iptv_sname':     result.name,
                    'iptv_muxname':   service_name,
                    'channel_number': result.number,
                    'iptv_epgid':     result.number
                }
                if run_mux_scan:
                    mux_conf['scan_state'] = 1
                tvh.idnode_save(mux_conf)
                # Save network UUID against playlist in settings
                source.tvh_uuid = mux_uuid
                db.session.commit()
                # Append to list of current network UUIDs
                existing_uuids.append(mux_uuid)

    #  TODO: Remove any muxes that are not managed. DONT DO THIS UNTIL THINGS ARE ALL WORKING!


def delete_channel_muxes(config, mux_uuid):
    tvh = get_tvh(config)
    tvh.delete_mux(mux_uuid)


def map_all_services(config):
    tvh = get_tvh(config)
    tvh.map_all_services_to_channels()


def cleanup_old_channels(config):
    tvh = get_tvh(config)
    for channel in tvh.list_all_channels():
        if channel.get('name') == "{name-not-set}":
            tvh.delete_channels(channel.get('uuid'))