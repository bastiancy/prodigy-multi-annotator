# coding: utf8
from __future__ import unicode_literals

import os
import uuid
import re
import shutil
import os.path
from celery import Celery
from celery.utils.log import get_logger
from app.settings import *


logger = get_logger(__name__)
celery = Celery('tasks', broker=CELERY_BROKER, backend=CELERY_BACKEND)


def make_prodigy(job_id, project_id, settings, logger, debug=False):
    import prodigy
    from app.database import connect

    if debug:
        os.environ["PRODIGY_LOGGING"] = 'basic'

    dbname = PRODIGY_CONFIG['db']
    connect(dbname, PRODIGY_CONFIG['db_settings'][dbname])

    loaded_recipe = prodigy.get_recipe(settings['recipe'])
    if not loaded_recipe:
        raise ValueError("Can't find recipe {}.".format(settings['recipe']))

    args = []   # to maintaint order of arguments
    for item in settings['recipe_sig']:
        if item in settings['recipe_args']:
            args.append(settings['recipe_args'][item])
        else:
            args.append(None)

    controller = loaded_recipe(*args)
    controller.config.update(PRODIGY_CONFIG)
    if 'config' in settings:
        controller.config.update(settings['config'])

    config = controller.config
    config['view_id'] = controller.view_id
    config['batch_size'] = controller.batch_size
    config['version'] = prodigy.about.__version__

    if 'instructions' in settings:
        help_path = Path('{}/{}'.format(DATA_DIR, settings['instructions']))
        if help_path.is_file():
            with help_path.open('r', encoding='utf8') as f:
                config['instructions'] = f.read()
        else:
            config['instructions'] = settings['instructions']

    for setting in ['db_settings', 'api_keys']:
        if setting in config:
            config.pop(setting)

    controller.save()
    return config, controller


class ProdigyJob(object):
    def __init__(self, job_id, project_id, settings, logger, debug=False):
        self.id = job_id
        self.uid = str(uuid.uuid4())[:8]
        self.logger = logger
        self.debug = debug
        self.config, self.controller = make_prodigy(self.id, project_id, settings, self.logger, self.debug)

    def get_project(self):
        self.logger.debug('CALLED "get_project" on job {} '.format(self.id))
        return self.config

    def get_questions(self):
        self.logger.debug('CALLED "get_questions" on job {} '.format(self.id))
        if self.controller.db and hasattr(self.controller.db, 'reconnect'):
            self.controller.db.reconnect()
        questions = self.controller.get_questions()
        result = {'tasks': questions, 'total': self.controller.total_annotated,
                  'progress': self.controller.progress}
        if self.controller.db and hasattr(self.controller.db, 'close'):
            self.controller.db.close()
        return result

    def give_answers(self, answers):
        self.logger.debug('CALLED "give_answers" on job {} with: '.format(self.id, repr(answers)))
        answers = answers['answers']
        if self.controller.db and hasattr(self.controller.db, 'reconnect'):
            self.controller.db.reconnect()
        self.controller.receive_answers(answers)
        result = {'progress': self.controller.progress}
        if self.controller.db and hasattr(self.controller.db, 'close'):
            self.controller.db.close()
        return result

    def get_stats(self):
        self.logger.debug('CALLED "get_stats" on job {} '.format(self.id))
        if self.controller.db and hasattr(self.controller.db, 'reconnect'):
            self.controller.db.reconnect()

        result = {'total': self.controller.total_annotated,
                  'progress': self.controller.progress,
                  'accept': 0, 'reject': 0, 'ignore': 0, 'meta': 0}

        if hasattr(self.config, 'meta'):
            result['meta'] = self.config['meta']

        if self.controller.db and hasattr(self.controller.db, 'close'):
            self.controller.db.close()
        return result


class ProdigyFactory(object):
    _jobs = {}

    def __init__(self):
        self.id = str(uuid.uuid4())[:8]
        logger.debug('_factory -> {}'.format(self.id))

    def get_job(self, job_id):
        logger.debug('_factory -> {}'.format(self.id))

        if job_id not in self._jobs:
            logger.debug('_jobs -> len: {}, repr: {}'.format(len(self._jobs), repr(self._jobs)))
            raise KeyError('invalid job_id "{}"'.format(job_id))

        return self._jobs[job_id]

    def create_job(self, job_id, project_id, user_id):
        logger.debug('_factory -> {}'.format(self.id))

        if job_id not in self._jobs:
            logger.warning('JOB "{}" IS STARTING'.format(job_id))

            if project_id not in ['manual_general']:
                # model shoud be copied per user
                orig = '{}/{}/model_v1'.format(DATA_DIR, project_id)
                dest = '{}/{}/jobs/{}/model_v1/'.format(DATA_DIR, project_id, job_id)
                if not os.path.exists(dest):
                    shutil.copytree(orig, dest)

            settings = PROJECTS[project_id]

            rep = {"{project_id}": project_id, "{user_id}": user_id, "{job_id}": job_id, "{base_path}": DATA_DIR}
            rep = dict((re.escape(k), v) for k, v in rep.items())
            pattern = re.compile("|".join(rep.keys()))

            for arg_name in settings['recipe_args']:
                if arg_name in ['dataset', 'spacy_model', 'source', '--patterns']:
                    text = settings['recipe_args'][arg_name]
                    text = pattern.sub(lambda m: rep[re.escape(m.group(0))], text)
                    settings['recipe_args'][arg_name] = text

            logger.info('JOB "{}" SETTINGS: {}'.format(job_id, repr(settings)))

            self._jobs[job_id] = ProdigyJob(job_id, project_id, settings, logger, False)
            job = self._jobs[job_id]
            logger.warning('JOB "{}" (uid: {}) IS READY'.format(job_id, job.uid))
        else:
            job = self._jobs[job_id]
            logger.warning('JOB "{}" (uid: {}) IS ALREADY RUNNING'.format(job_id, job.uid))

        logger.debug('_jobs -> len: {}, repr: {}'.format(len(self._jobs), repr(self._jobs)))
        return job


class ProdigyTask(celery.Task):

    def __init__(self):
        self.jobs = ProdigyFactory()


class SpacyTask(celery.Task):
    _models = {}

    @property
    def model(self, name):
        if not name in self._models:
            import spacy
            self._models[name] = spacy.load(name)

        return self._models[name]


@celery.task(bind=True, base=ProdigyTask)
def start_job(self, job_id, project_id, user_id):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    job = self.jobs.create_job(job_id, project_id, user_id)
    job = self.jobs.get_job(job.id)
    return self.request.hostname, job.id, job.uid


@celery.task(bind=True, base=ProdigyTask)
def get_project(self, job_id):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    job = self.jobs.get_job(job_id)
    return job.get_project()


@celery.task(bind=True, base=ProdigyTask)
def get_questions(self, job_id):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    job = self.jobs.get_job(job_id)
    return job.get_questions()


@celery.task(bind=True, base=ProdigyTask)
def give_answers(self, job_id, data):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    job = self.jobs.get_job(job_id)
    return job.give_answers(data)


@celery.task(bind=True, base=ProdigyTask)
def get_stats(self, job_id):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    job = self.jobs.get_job(job_id)
    return job.get_stats()


@celery.task(bind=True)
def train_models(self):
    # train each model independently
    rep = {"{project_id}": project_id, "{user_id}": user_id, "{job_id}": job_id, "{base_path}": DATA_DIR}
    rep = dict((re.escape(k), v) for k, v in rep.items())
    pattern = re.compile("|".join(rep.keys()))

    for project_id in PROJECTS:
        settings = PROJECTS[project_id]

        for user_id in USERS:
            job_id = 'prodigy.{}.{}'.format(project_id, user_id)
            orig = '{}/{}/jobs/{}/model_v1/'.format(DATA_DIR, project_id, job_id)
            
    # train model_general 


@celery.task(bind=True, base=SpacyTask)
def get_prediction(self, text, modelname, only_ents=True):
    logger.debug('Executing task id {0.id}, args: {0.args!r} kwargs: {0.kwargs!r}'.format(self.request))
    nlp = self.model(modelname)
    doc = nlp(text)
    if only_ents:
        return list(doc.ents)
    else:
        return doc
