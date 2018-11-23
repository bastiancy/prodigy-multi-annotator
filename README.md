Prodigy Multi Annotator
=======================

This is my attempt for using the amazing tool [prodigy](https://prodi.gy/) with muliple users. It's just a basic web-based annotation maganer that I created for my spcecific needs.

It allows you to run muliple recipes, and with many users per recipe. It uses celery underneath to create a queue per user/recipe, so your annotators can start working on multiple tasks, and resume where they left at any time.

Celery also allows you to spin up multiple workers, so you can run the recipes in parallel, or on multiple machines.

## Setup

This project uses [Docker](https://docs.docker.com/install/linux/docker-ce/ubuntu/) and [Docker Compose](https://docs.docker.com/compose/install/), make sure you have installed them before continuing.

```
clone https://github.com/bastiancy/prodigy-multi-annotator
cd prodigy-multi-annotator

# You need to copy your own prodigy binary, as its a dependency for the docker image
cp /tmp/prodigy-1.5.1-cp35.cp36-cp35m.cp36m-linux_x86_64.whl ./docker/

docker-compose -f compose-dev up -d --build
```

There is not [spaCy models](https://spacy.io/models/) installed on the image, so you need to add them manually

```
docker-compose -f compose-dev exec worker python3 -m spacy download en_core_web_sm
```

If you are not running the project locally, the `BASE_URL` must be set on the `compose-dev.yml` file (i.e. `BASE_URL=http://prodigy.mysite.com`)

Docker mounts the folder `./data` to the containers, here you can add files that the recipes can use, e.x. to load a custom model, or load a jsonl source file.

## Usage

First, you need to configure what recipes will be available for users, I call this **projects**. Add them in the `src/config.py` file.

```python
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
        'users': ['john', 'jane'],
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
```

## Limitations

Currently, I'm not able to config Celery for proper concurrency, so I run the workers with the `--concurrency=1` flag. But, you can run multiple workers with docker using the command `docker-compose -f compose-dev.yml scale worker=4`; this runs 4 celery workers on the same machine, then when a user starts a task the applicaction will choose randomly one worker and will stick to it.

The application does not cache resources between recipes nor workers, so for every user starting a recipe the spacy model will be loaded into memory. You should make sure you have enough memory to run your recipes for all users.

## Todo

 - allow consolidation of annotations, and re-train models periodicaly.
 - config Celery for proper concurrency.
 - implement resource caching for concurrency.

## Licence

