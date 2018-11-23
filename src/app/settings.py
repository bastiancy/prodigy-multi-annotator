# coding: utf8
from __future__ import unicode_literals

from os import environ


DEBUG = True
SECRET_KEY = 'hin6bab8ge25*r=x&amp;+5$0kn=-#log$pt^#@vrqjld!^2ci@g*b'
BASE_URL = environ.get('BASE_URL', 'http://127.0.0.1')
DATA_DIR = environ.get('DATA_DIR', '../data')
CELERY_BROKER = environ.get('CELERY_BROKER', 'redis://192.168.99.100:6379/0')
CELERY_BACKEND = environ.get('CELERY_BACKEND', 'redis://192.168.99.100:6379/0')

PRODIGY_CONFIG = {
    "db": "postgresql",
    "db_settings": {
        "postgresql": {
            "host": environ.get('DB_HOST'),
            "port": 5432,
            "dbname": "prodigy",
            "user": environ.get('DB_USER'),
            "password": environ.get('DB_PASS')
        },
        "sqlite": {
            "name": "prodigy.db",
            "path": DATA_DIR
        }
    },
    "theme": "basic",
    "custom_theme": {},
    "batch_size": 10,
    "port": 8080,
    "host": "0.0.0.0",
    "validate": True,
    "auto_create": True,
    "show_stats": True,
    "hide_meta": False,
    "show_flag": False,
    "instructions": False,
    "swipe": False,
    "split_sents_threshold": True,
    "diff_style": "words",
    "html_template": False,
    "card_css": {},
    "writing_dir": "ltr",
    "hide_true_newline_tokens": False,
    "ner_manual_require_click": False,
    "ner_manual_label_style": "list",
    "choice_style": "single",
    "choice_auto_accept": False,
    "darken_image": 0,
    "show_bounding_box_center": False,
    "preview_bounding_boxes": False,
    "shade_bounding_boxes": False
}
USERS = {
    'bcarvajal': {'username': 'bcarvajal', 'password': 'ppba', 'name': 'Bastian Carvajal'},
    'carroyo': {'username': 'carroyo', 'password': 'ppba', 'name': 'Cristian Arroyo'},
    'csobarzo': {'username': 'csobarzo', 'password': 'ppba', 'name': 'Cristian Sobarzo'},
    'mcepeda': {'username': 'mcepeda', 'password': 'ppba', 'name': 'Maurice Cepeda'},
    'jmleon': {'username': 'jmleon', 'password': 'ppba', 'name': 'Jose Manuel Leon'},
    'emartin': {'username': 'emartin', 'password': 'ppba', 'name': 'Eric Martin'},
    'raguirre': {'username': 'raguirre', 'password': 'ppba', 'name': 'Rodrigo Aguirre'},
    'jccarmona': {'username': 'jccarmona', 'password': 'ppba', 'name': 'Juan Christian Carmona'},
    'mrodriguez': {'username': 'mrodriguez', 'password': 'ppba', 'name': 'Mauricio Rodriguez'},
    'amrugaslki': {'username': 'amrugaslki', 'password': 'ppba', 'name': 'Alan Mrugalski'},
    'cmerino': {'username': 'cmerino', 'password': 'ppba', 'name': 'Carola Merino'},
}
PROJECTS = {
    'manual_all': {
        'recipe': 'ner.manual',
        'recipe_sig': ('dataset', 'spacy_model', 'source', '--api', '--loader', '--label', '--exclude'),
        'recipe_args': {
            'dataset': 'manual_all.{user_id}',
            'spacy_model': 'en_core_web_sm',
            'source': '{data_dir}/manual_all/source.jsonl',
            '--label': ('PER', 'ORG', 'LOC')
        },
        'config': {
            'show_stats': False,
            'swipe': False,
        },
        'desc': 'Manually annotate examples for labels: PER, ORG and LOC.',
        'instructions': '{data_dir}/manual_all/instructions.html',
        'visible': True
    },
    'teach_org': {
        'recipe': 'ner.teach',
        'recipe_sig': ('dataset', 'spacy_model', 'source', '--api', '--loader', '--label', '--patterns', '--exclude', '--unsegmented'),
        'recipe_args': {
            'dataset': 'teach_org.{user_id}',
            'spacy_model': '{data_dir}/teach_org/{user_id}/model',
            'source': '{data_dir}/teach_org/source.jsonl',
            '--label': ('ORG',),
        },
        'desc': 'Validate algorithm predictions, for label "ORG".',
        'instructions': '{data_dir}/teach_org/instructions.html',
        'visible': True,
        'only_user': ['john', 'jane'],
        'copy_model': ('{data_dir}/teach_org/model', '{data_dir}/teach_org/{user_id}/model'),
    },
    'train_all': {
        'recipe': 'ner.batch-train',
        'recipe_sig': ('dataset', 'spacy_model', '--output', '--factor', '--dropout', '--n-iter', '--batch-size', '--beam-width', '--eval-id', '--eval-split', '--unsegmented', '--no-missing', '--silent'),
        'recipe_args': {
            'dataset': 'train_all',
            'spacy_model': '{data_dir}/manual_all/model',
            '--factor': 1,
            '--output': '{data_dir}/manual_all/model_v2',
            '--eval-id': 'eval_all',
        },
        'visible': False,
        'consolidate': {
            'source': ['teach_org.{user_id}', 'manual_all.{user_id}'],
            'dest': 'train_all',
        },
        'copy_model': ('{data_dir}/manual_all/model_v2', '{data_dir}/teach_org/model')
    }
}
