#!/usr/bin/env python3

import database
import hashlib
import random
import requests
import random
import sys
import urllib

import verification

def ListSubscriptions(db_path, hub_url, topic_url):
    db = database.SubscriptionsDb(db_path)
    for sub in db.FindSubscriptions(hub_url=hub_url, topic_url=topic_url):
        # TODO: nicer formatting?
        print(sub)
    return True


# This calls <callback_base_url>?validate=random-challenge to verify the
# callback URL is accessible (might still be firewalled though).
def VerifyCallback(callback_base_url):
    challenge = verification.GenerateChallenge()
    response_text = verification.GenerateResponse(challenge)
    response = requests.get(callback_base_url, params={'validate': challenge})
    if response.status_code != 200:
        raise Exception('Unexpected status code: %d', response.status_code)
    if response.text.strip() != response_text:
        raise Exception('Incorrect response text')
    print('Endpoint verification succesfull')


def _MakeCallbackUrl(callback_base_url, sub):
    return callback_base_url + '/' + urllib.parse.quote(sub.subscription_id, safe='')


def Subscribe(db_path, callback_base_url, hub_url, topic_url, lease_seconds=None):
    db = database.SubscriptionsDb(db_path)
    sub = db.CreateSubscription(hub_url, topic_url)
    data = {
        'hub.mode': 'subscribe',
        'hub.callback': _MakeCallbackUrl(callback_base_url, sub),
        'hub.topic': topic_url,
    }
    if lease_seconds is not None:
        data['hub.lease_seconds'] = str(int(lease_seconds))  # truncate float
    response = requests.post(hub_url, data=data)
    if response.status_code != 202:  # Accepted
        raise Exception('Unexpected response code from hub: %d' % (response.status_code,))
    # TODO: catch exception that occurs when subscription is already in "subscribed" state
    db.ChangeSubscriptionState(sub, 'subscribe-pending', ('subscribing', 'subscribe-pending'))
    print(sub)


def Unsubscribe(db_path, callback_base_url, subscription_id):
    db = database.SubscriptionsDb(db_path)
    sub = db.ReadSubscription(subscription_id)
    if not sub:
        raise Exception('Subscription not found')
    db.ChangeSubscriptionState(sub, 'unsubscribing', ('subscribed', 'unsubscribing', 'unsubscribe-pending'))
    data = {
        'hub.mode': 'unsubscribe',
        'hub.callback': _MakeCallbackUrl(callback_base_url, sub),
        'hub.topic': sub.topic_url,
    }
    response = requests.post(sub.hub_url, data=data)
    if response.status_code != 202:  # Accepted
        raise Exception('Unexpected response code from hub: %d' % (response.status_code,))
    # TODO: catch exception that occurs when subscription is already in "unsubscribed" state
    db.ChangeSubscriptionState(sub, 'unsubscribe-pending', ('unsubscribing', 'unsubscribe-pending'))


def PrintUsage(argv0):
    print('Usage:')
    print('\t' +  argv0 + ' subscribe   <database> <callback-base-url> <hub-url> <topic-url> [<lease-seconds>]')
    print('\t' +  argv0 + ' unsubscribe <database> <callback-base-url> <subscription-id>')
    print('\t' +  argv0 + ' list        <database> <hub-url> <topic-url>')
    print('\t' +  argv0 + ' verify      <callback-base-url>')


def HandleArgs(args):
    if len(args) < 1:
        return False

    if args[0] == 'subscribe':
        if len(args) < 5 or len(args) > 6: return False
        Subscribe(*args[1:])
        
    elif args[0] == 'unsubscribe':
        if len(args) != 4: return False
        Unsubscribe(*args[1:])

    elif args[0] == 'list':
        if len(args) != 4: return False
        ListSubscriptions(*args[1:])

    elif args[0] == 'verify':
        if len(args) != 2: return False
        VerifyCallback(*args[1:])

    else:
        print('Unsupported command:', args[0], file=sys.stderr)
        return False

    return True

if __name__ == '__main__':
    if not HandleArgs(sys.argv[1:]):
        PrintUsage(sys.argv[0])
        sys.exit(len(sys.argv) > 1)
