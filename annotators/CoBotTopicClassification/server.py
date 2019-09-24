#!/usr/bin/env python

import json
import logging
import os
import uuid
import time

import requests
from flask import Flask, request, jsonify
from os import getenv
import sentry_sdk


sentry_sdk.init(getenv('SENTRY_DSN'))


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

COBOT_API_KEY = os.environ.get('COBOT_API_KEY')
COBOT_TOPICS_SERVICE_URL = os.environ.get('COBOT_TOPICS_SERVICE_URL')

if COBOT_API_KEY is None:
    raise RuntimeError('COBOT_API_KEY environment variable is not set')
if COBOT_TOPICS_SERVICE_URL is None:
    raise RuntimeError('COBOT_TOPICS_SERVICE_URL environment variable is not set')

headers = {'Content-Type': 'application/json;charset=utf-8', 'x-api-key': f'{COBOT_API_KEY}'}


@app.route("/topics", methods=['POST'])
def respond():
    st_time = time.time()
    user_sentences = request.json['sentences']
    session_id = uuid.uuid4().hex
    topics = []
    confidences = []
    result = requests.request(url=f'{COBOT_TOPICS_SERVICE_URL}',
                              headers=headers,
                              data=json.dumps({'utterances': user_sentences}),
                              method='POST').json()

    for i, sent in enumerate(user_sentences):
        logger.info(f"user_sentence: {sent}, session_id: {session_id}")
        topic = result["topics"][i]["topicClass"]
        confidence = result["topics"][i]["confidence"]
        topics += [topic]
        confidences += [confidence]
        logger.info(f"topic: {topic}")
    total_time = time.time() - st_time
    logger.info(f'cobot_topics exec time: {total_time:.3f}s')
    return jsonify(list(zip(topics, confidences)))


if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=3000)
