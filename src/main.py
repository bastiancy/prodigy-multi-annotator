# coding: utf8
from __future__ import unicode_literals

import random
import logging
from hashlib import md5
from functools import wraps
from pathlib import Path

from flask import Flask, g, request, Response, json, render_template, send_from_directory, session, abort, flash, redirect, url_for
from flask_cors import CORS, cross_origin
from app.settings import *
from app.database import connect, User
from app.tasks import start_job, get_project, get_questions, give_answers, get_stats


web = Flask(__name__)
web.config.from_object(__name__)
CORS(web, supports_credentials=True)
DB = connect(PRODIGY_CONFIG['db'], PRODIGY_CONFIG['db_settings'][PRODIGY_CONFIG['db']])


def auth_user(user):
    session['logged_in'] = True
    session['user_id'] = user.id
    session['username'] = user.username
    flash('You are logged in as %s' % (user.username))


def get_current_user():
    if session.get('logged_in'):
        return User.get(User.id == session['user_id'])


def login_required(f):
    @wraps(f)
    def inner(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return inner


@web.before_first_request
def setup_logging():
    if not web.debug:
        web.logger.addHandler(logging.StreamHandler())
        web.logger.setLevel(logging.INFO)


# @web.before_request
# def before_request():
#     g.db = database
#     g.db.connect()
#
#
# @web.after_request
# def after_request(response):
#     g.db.close()
#     return response


@web.route('/login/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST' and request.form['username']:
        try:
            pw_hash = md5(request.form['password'].encode('utf-8')).hexdigest()
            user = User.get(
                (User.username == request.form['username']) &
                (User.password == pw_hash))
        except User.DoesNotExist:
            web.logger.error('[DEBUG] pass: %s, hash: %s', request.form['password'], pw_hash)
            flash('The password entered is incorrect')
        else:
            auth_user(user)
            return redirect(url_for('task_list'))

    return render_template('login.html')


@web.route('/logout/')
def logout():
    session.pop('logged_in', None)
    flash('You were logged out')
    return redirect(url_for('task_list'))


@web.context_processor
def _inject_user():
    return {'current_user': get_current_user()}


@web.route('/')
@login_required
def task_list():
    user = get_current_user()
    available_projects = []
    for key, value in PROJECTS.items():
        # skip if not visible, or if user is not in only_user list (if not defined all users are allowed)
        if value['visible'] != True or ('only_user' in value and user.username not in value['only_user']):
            continue

        item = {'name': key, 'desc': value['desc'], 'stats': []}

        if 'instructions' in value:
            help_path = Path('{}/{}'.format(DATA_DIR, value['instructions']))
            if help_path.is_file():
                with help_path.open('r', encoding='utf8') as f:
                    item['instructions'] = f.read()
            else:
                item['instructions'] = value['instructions']

        available_projects.append(item)

    context = {'base_url': BASE_URL, 'projects': available_projects}
    return render_template('task_list.html', **context)


@web.route('/login')
def web_login():
    context = {'base_url': BASE_URL}
    content = render_template('login.html', **context)
    return Response(content, mimetype='text/html')


@web.route('/static/<path:path>')
def send_static(path):
    return send_from_directory('static', path)


@web.route('/fonts/<path:path>')
def send_fonts(path):
    return send_from_directory('static/fonts', path)


@web.route('/prodigy/<job>/index.html')
def prodigy_index(job):
    context = {'base_url': BASE_URL, 'job': job}
    content = render_template('prodigy/index.html', **context)
    return Response(content, mimetype='text/html')


@web.route('/prodigy/<job_id>/project')
def prodigy_get_project(job_id):
    """Get the meta data and configuration of the current project.
    RETURNS (dict): The configuration parameters and settings.
    """
    reply = get_project.apply_async(args=(job_id,),
                                    queue=job_id)
    result = reply.get()
    # print('[CLIENT] call "get_project" for job {} responded with: {}'.format(job_id, repr(result)))
    return Response(json.dumps(result), mimetype='application/json')


@web.route('/prodigy/<job_id>/get_questions')
def prodigy_get_questions(job_id):
    """Get the next batch of tasks to annotate.
    RETURNS (dict): {'tasks': list, 'total': int, 'progress': float}
    """
    reply = get_questions.apply_async(args=(job_id,),
                                      queue=job_id)
    result = reply.get()
    # print('[CLIENT] call "get_questions" for job {} responded with: {}'.format(job_id, repr(result)))
    return Response(json.dumps(result), mimetype='application/json')


@web.route('/prodigy/<job_id>/give_answers', methods=['POST'])
def prodigy_give_answers(job_id):
    """Receive annotated answers, e.g. from the web app.
    answers (list): A list of task dictionaries with an added `"answer"` key.
    RETURNS (dict): {'progress': float}
    """
    if not request.is_json:
        raise KeyError('answers not valid')

    data = request.get_json(force=True, cache=False)
    reply = give_answers.apply_async(args=(job_id, data),
                                      queue=job_id)
    result = reply.get()
    # print('[CLIENT] call "get_questions" for job {} responded with: {}'.format(job_id, repr(result)))
    return Response(json.dumps(result), mimetype='application/json')


@web.route('/prodigy/<path:path>')
def prodigy_static(path):
    from prodigy.app import serve_static
    base = serve_static()
    return send_from_directory(base[0], path)


@web.route("/api/project")
def project_list():
    user = None
    content = []
    for key, value in PROJECTS.items():
        # skip if not visible, or if user is not in only_user list (if not defined all users are allowed)
        if value['visible'] != True or ('only_user' in value and user.username not in value['only_user']):
            continue

        item = {'name': key, 'desc': value['desc']}

        if 'instructions' in value:
            help_path = Path('{}/{}'.format(DATA_DIR, value['instructions']))
            if help_path.is_file():
                with help_path.open('r', encoding='utf8') as f:
                    item['instructions'] = f.read()
            else:
                item['instructions'] = value['instructions']

        content.append(item)

    return Response(json.dumps(content), mimetype='application/json')


@web.route("/api/project/<project_id>/stats/<user_id>")
def project_stat_for_user(project_id, user_id):
    job_id = 'prodigy.{}.{}'.format(project_id, user_id)

    reply = get_stats.apply_async(args=(job_id,),
                                  queue='prodigy',
                                  routing_key=job_id)
    result = reply.get()
    # print('[CLIENT] call "get_stats" for job {} responded with: {}'.format(job_id, repr(result)))

    return Response(json.dumps(result), mimetype='application/json')


@web.route("/api/project/<project>/comments/<username>", methods=['GET', 'POST'])
def project_comments_for_user(project, username):
    content = {'comments': ''}
    return Response(json.dumps(content), mimetype='application/json')


@web.route("/api/project/<project_id>/start_job/<user_id>")
def project_create_job(project_id, user_id):
    job_id = 'prodigy.{}.{}'.format(project_id, user_id)

    # retry = 3
    # while retry > 0:
    #     workers = app.control.inspect().stats()
    #     web.logger.info('[API-INFO] stats: %r', workers)
    #
    #     if len(workers) == 0:
    #         retry -= 1
    #         web.logger.info('[API-INFO] no active workers. retry %i', retry)
    #         time.sleep(0.1)
    #     else:
    #         break

    workers = celery.control.inspect().stats()
    web.logger.debug('[DEBUG] workers: %r', workers)

    queues = celery.control.inspect().active_queues()
    web.logger.debug('[DEBUG] active_queues: %r', queues)

    active_queue = None
    for worker in queues:
        for queue in queues[worker]:
            if queue['name'] == job_id:
                active_queue = (worker, queue)
                break

    if active_queue is None:
        worker, _ = random.choice(list(workers.items()))
        web.logger.info('[INFO] bind queue %s to worker %s', job_id, worker)
        reply = celery.control.add_consumer(
            destination=(worker,),
            queue=job_id,
            exchange='prodigy',
            exchange_type='direct',
            options={
                'queue_durable': True,
                'exchange_durable': True,
            },
            reply=True)
        web.logger.debug('[INFO] bind result: %r', reply)

        reply = start_job.apply_async((job_id, project_id, user_id), queue=job_id)
        hostname, job_id, job_uid = reply.get()
        web.logger.info('[INFO] response from control - hostname: %s, job_id: %s, job_uid: %s', hostname, job_id, job_uid)
    else:
        web.logger.info('[INFO] running in worker: %s', active_queue[0])

    result = {'url': '/prodigy/{}/index.html'.format(job_id)}
    return Response(json.dumps(result), mimetype='application/json')


@web.route("/api/user/login", methods=['POST'])
def user_login():
    username = request.form['username']

    if not username or username not in USERS:
        raise KeyError('username not valid!')

    user = USERS[username]
    password = request.form['password']

    if not password or password != user['password']:
        raise KeyError('password not valid!')

    content = {'token': username, 'name': user['name']}
    return Response(json.dumps(content), mimetype='application/json')


@web.route("/api/user/logout")
def user_logout():
    content = {'status': 'ok'}
    return Response(json.dumps(content), mimetype='application/json')


if __name__ == '__main__':
    web.run(debug=True, host='0.0.0.0', port=8080)
