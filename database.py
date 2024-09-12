import sqlite3

import logging
import random
import secrets
import time
from dataclasses import dataclass


# Describes possible states for each subscription.
#
# Feeds must go through states in order, though the PENDING states can be
# skipped if # hub confirms the (un)subscription while the request t
# (un)subscribe is in progress.
# Possible lifecycles:
#
# SUBSCRIBING -> SUBSCRIBE_PENDING -> SUBSCRIBED -> UNSUBSCRIBING -> UNSUBSCRIBE_PENDING -> UNSUBSCRIBED
# SUBSCRIBING -> SUBSCRIBE_PENDING -> DENIED
# SUBSCRIBING -> SUBSCRIBE_PENDING -> SUBSCRIBED -> DENIED
#
class SubscriptionState:
    # Initial state. Client intends to subscribe, but hub has not yet been called.
    SUBSCRIBING = 'subscribing'

    # Client has made a subscribe request to the hub, but no reply received yet.
    SUBSCRIBE_PENDING = 'subscribe-pending'

    # Hub has confirmed the subscription.
    SUBSCRIBED = 'subscribed'

    # Hub has denied the subscription.
    DENIED = 'denied'

    # Client intends to unsubscribe, but hub has not yet been called.
    UNSUBSCRIBING = 'unsubscribing'

    # Client has made an unsubscribe request to the hub, but no reply received yet.
    UNSUBSCRIBE_PENDING = 'unsubscribe-pending'

    # Hub has confirmed the unsubscription.
    UNSUBSCRIBED = 'unsubscribed'


@dataclass
class Subscription:
    subscription_id: str
    hub_url: str
    topic_url: str
    secret: str  # unused
    state: str
    last_modified: float
    expires_at: float


class SubscriptionsDb:
    def __init__(self, db_path):
        self.db = sqlite3.connect(db_path, autocommit=True)
        # TODO: should also close the db at some point!

    def CreateSubscription(self, hub_url, topic_url):
        subscription_id = secrets.token_urlsafe(18)  # 18 * 8 = 144 bits of entropy
        sub = Subscription(subscription_id=subscription_id, topic_url=topic_url, hub_url=hub_url, secret=None, state=SubscriptionState.SUBSCRIBING, last_modified=time.time(), expires_at=None)
        self.db.execute('INSERT INTO subscriptions(subscription_id, hub_url, topic_url, secret, state, last_modified, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                (sub.subscription_id, sub.hub_url, sub.topic_url, sub.secret, sub.state, sub.last_modified, sub.expires_at))
        return sub

    def ReadSubscription(self, subscription_id):
        row = self.db.execute('SELECT hub_url, topic_url, secret, state, last_modified, expires_at FROM subscriptions WHERE subscription_id=?', (subscription_id,)).fetchone()
        if not row: return None
        hub_url, topic_url, secret, state, last_modified, expires_at = row
        return Subscription(subscription_id=subscription_id, hub_url=hub_url, topic_url=topic_url, secret=secret, state=state, last_modified=last_modified, expires_at=expires_at)

    def FindSubscriptions(self, hub_url, topic_url):
        cur = self.db.execute('SELECT subscription_id, secret, state, last_modified, expires_at FROM subscriptions WHERE hub_url=? AND topic_url=?', (hub_url, topic_url))
        results = []
        for subscription_id, secret, state, last_modified, expires_at in cur.fetchall():
            results.append(Subscription(subscription_id=subscription_id, hub_url=hub_url, topic_url=topic_url, secret=secret, state=state, last_modified=last_modified, expires_at=expires_at))
        return results

    def ChangeSubscriptionState(self, sub, new_state, old_states, lease_seconds=-1):
        assert sub.state in old_states
        last_modified = time.time()
        expires_at = last_modified + lease_seconds if lease_seconds >= 0 else None
        cur = self.db.execute(
                "UPDATE subscriptions SET state=?, last_modified=?, expires_at=? WHERE subscription_id=? AND state IN (" + ','.join(tuple('?'*len(old_states))) + ")",
                (new_state, last_modified, expires_at, sub.subscription_id) + old_states)
        if cur.rowcount != 1:
            raise Exception("Could not transition subscription %s from %s to %s" % (sub.subscription_id, sub.state, new_state))
        sub.state = new_state
        sub.last_modified = last_modified
        sub.expires_at = expires_at

    def ConfirmSubscription(self, sub, lease_seconds):
        self.ChangeSubscriptionState(sub, SubscriptionState.SUBSCRIBED, (SubscriptionState.SUBSCRIBING, SubscriptionState.SUBSCRIBE_PENDING, SubscriptionState.SUBSCRIBED), lease_seconds=lease_seconds)

    def DenySubscription(self, sub, reason):
        # TODO later: store reason in db for debugging?
        self.ChangeSubscriptionState(sub, SubscriptionState.DENIED, (SubscriptionState.SUBSCRIBING, SubscriptionState.SUBSCRIBE_PENDING, SubscriptionState.SUBSCRIBED, SubscriptionState.DENIED), lease_seconds=-1)

    def ConfirmUnsubscription(self, sub):
        self.ChangeSubscriptionState(sub, SubscriptionState.UNSUBSCRIBED, (SubscriptionState.UNSUBSCRIBING, SubscriptionState.UNSUBSCRIBE_PENDING, SubscriptionState.UNSUBSCRIBED), lease_seconds=-1)

    def AddUpdate(self, sub, content_type, content):
        # Maybe: get topic_url and hub_url from Link header instead?
        # (According to the docs they may change. Not sure what to do with that though.)
        self.db.execute('INSERT INTO updates(subscription_id, hub_url, topic_url, timestamp, content_type, content) VALUES (?, ?, ?, ?, ?, ?)',
            (sub.subscription_id, sub.hub_url, sub.topic_url, time.time(), content_type, content))
