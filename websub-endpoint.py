#!/usr/bin/env python3

import argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
import logging
import sys
from urllib.parse import urlparse, parse_qs

from database import SubscriptionsDb, SubscriptionState
import verification

db = None


class RequestHandler(BaseHTTPRequestHandler):

    def _SendPlainTextResponse(self, response):
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.end_headers()
        self.wfile.write(response.encode('utf-8'))


    def do_GET(self):
        logging.info("GET %s\n%s", self.path, self.headers)

        url = urlparse(self.path)

        # Parse query string, but only keep last value for each key.
        query = dict((key, values[-1]) for (key, values) in parse_qs(url.query).items())

        if url.path == '/subscriptions':
            challenge = query.get('validate', None)
            if not challenge:
                self.send_error(400, explain='Missing challenge')
                return
            return self._SendPlainTextResponse(verification.GenerateResponse(challenge))

        if url.path.startswith('/subscriptions/'):
            subscription_id = url.path[len('/subscriptions/'):]
            sub = db.ReadSubscription(subscription_id)
            if not sub:
                logging.warning("Subscription not found: %s", subscription_id)
                self.send_error(404)
                return
            
            # Verification request:
            # /?hub.topic=https://styx.verver.ch/~maks/test-atom-feed.xml&hub.challenge=1064400762185457246&hub.mode=subscribe&hub.lease_seconds=432000
             
            hub_mode = query.get('hub.mode', None)
            hub_topic = query.get('hub.topic', None)
            hub_reason = query.get('hub.reason', None)
            hub_challenge = query.get('hub.challenge', None)
            hub_lease_seconds = query.get('hub.lease_seconds', None)

            if hub_mode == 'subscribe' and hub_topic and hub_challenge and hub_lease_seconds:
                try:
                    hub_lease_seconds = int(hub_lease_seconds)
                except:
                    logging.warning("Failed to parse hub.lease_seconds argument: %s", hub_lease_seconds)
                    self.send_error(400)  # Bad request
                    return

                # Subscription validation
                if hub_topic != sub.topic_url:
                    logging.warning("Subscription %s topic url (%s) does not match hub topic url (%s)", subscription_id, sub.topic_url, hub_topic)
                    self.send_error(400)  # Bad request
                    return

                if sub.state not in (SubscriptionState.SUBSCRIBING, SubscriptionState.SUBSCRIBED):
                    logging.warning("Received subscription request for subscription %s in state %s", subscription_id, sub.state)
                    self.send_error(400)  # Bad request
                    return

                db.ConfirmSubscription(sub, hub_lease_seconds)
                return self._SendPlainTextResponse(hub_challenge)

            if hub_mode == 'unsubscribe' and hub_topic and hub_challenge:
                if hub_topic != sub.topic_url:
                    logging.warning("Subscription %s topic url (%s) does not match hub topic url (%s)", subscription_id, sub.topic_url, hub_topic)
                    self.send_error(400)  # Bad request
                    return

                if sub.state not in (SubscriptionState.UNSUBSCRIBING, SubscriptionState.UNSUBSCRIBED):
                    logging.warning("Received unsubscription request for subscription %s in state %s", subscription_id, sub.state)
                    self.send_error(400)  # Bad request
                    return

                db.ConfirmUnsubscription(sub)
                return self._SendPlainTextResponse(hub_challenge)

            if hub_mode == SubscriptionState.DENIED and hub_topic:
                logging.warning("Subscription %s was denied (reason: %s)", subscription_id, hub_reason)
                db.DenySubscription(sub, hub_reason)
                # Alternatively, we could send 204 No Content, but it looks weird in the browser (no page refresh)
                # and the spec doesn't require any particular status code here.
                self.send_response(200)  # OK
                self.end_headers()
                return

            # If nothing else matched, the wrong set of parameters was passed, so send a generic client error
            # instead of 404, because we already confirmed the subscription does exist
            self.send_error(400)  # Bad request
            return

        # If nothing else matched, path was invalid:
        self.send_error(404)
        return
   

    def do_POST(self):
        logging.info("POST %s\n%s", self.path, self.headers)

        url = urlparse(self.path)

        if url.path.startswith('/subscriptions/'):
            subscription_id = url.path[len('/subscriptions/'):]
            sub = db.ReadSubscription(subscription_id)
            if not sub or sub.state not in (SubscriptionState.SUBSCRIBING, SubscriptionState.SUBSCRIBED):
                # 410 Gone should cause the hub to unsubscribe and stop posting data.
                logging.warning("Received POST request for subscription %s in state %s", subscription_id, sub.state if sub is not None else 'Not found')
                self.send_error(410)  # Gone
                return

            if 'Content-Type' not in self.headers or 'Content-Length' not in self.headers:
                logging.warning('Received POST request without Content-Type and/or Content-Length')
                self.send_error(400)  # Bad Request
                return
                    
            content_type = self.headers['Content-Type']
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            assert len(post_data) == content_length  # or do we need to read in a loop to get all data?
            logging.info("POST data: %s", post_data)

            db.AddUpdate(sub, content_type, post_data)

            self.send_response(202)  # Accepted
            self.end_headers()
            return

        # If nothing else matched, path was invalid:
        self.send_error(404)
        return


def run(server_class=HTTPServer, handler_class=RequestHandler, server_address=('localhost', '8000')):
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(prog='websub-handler')
    parser.add_argument('--loglevel', default='WARNING')
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--port', default=8080)
    parser.add_argument('database')
    args = parser.parse_args()
    logging.basicConfig(level=getattr(logging, args.loglevel))
    db = SubscriptionsDb(args.database)
    run(server_address=(args.host, args.port))
